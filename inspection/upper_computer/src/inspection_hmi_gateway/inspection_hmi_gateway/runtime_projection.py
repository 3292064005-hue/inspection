from __future__ import annotations

"""Projection and artifact helpers for the gateway runtime."""

from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
import time
import uuid

if TYPE_CHECKING:
    from inspection_interfaces.msg import CountStats, FaultEvent, InspectionResult, StationState
else:
    CountStats = FaultEvent = InspectionResult = StationState = Any

from inspection_utils.logging_tools import safe_json_loads
from inspection_utils.paths import relative_artifact_path

from .runtime_components import _safe_float, _safe_int, normalize_mode, normalize_phase, ros_time_to_iso, to_health, utc_now


class PendingCorrelationStore:
    """TTL bounded correlation cache for result/decision joins."""

    def __init__(self, *, max_entries: int = 512, ttl_sec: float = 300.0) -> None:
        self.max_entries = max(1, int(max_entries))
        self.ttl_sec = max(1.0, float(ttl_sec))
        self._items: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()

    def put(self, key: str, payload: dict[str, Any]) -> None:
        self.prune()
        if key in self._items:
            self._items.pop(key, None)
        self._items[key] = (time.monotonic(), dict(payload))
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)

    def get(self, key: str) -> dict[str, Any] | None:
        self.prune()
        item = self._items.get(key)
        return None if item is None else dict(item[1])

    def pop(self, key: str) -> dict[str, Any] | None:
        item = self._items.pop(key, None)
        return None if item is None else dict(item[1])

    def prune(self) -> None:
        deadline = time.monotonic() - self.ttl_sec
        stale_keys = [key for key, (created_at, _payload) in self._items.items() if created_at < deadline]
        for key in stale_keys:
            self._items.pop(key, None)


class GatewayArtifactResolver:
    """Sanitize and project runtime artifact paths into gateway URLs."""

    def __init__(self, log_root: str | Path) -> None:
        self.log_root = Path(log_root)

    def artifact_url(self, path: str | Path) -> str:
        raw = str(path or '').strip()
        if not raw:
            return ''
        try:
            normalized = relative_artifact_path(self.log_root, raw)
        except ValueError:
            return ''
        return f'/artifacts/{normalized}'


class GatewayReadModelProjector:
    """Project ROS topics into gateway read models and HMI events."""

    def __init__(
        self,
        *,
        state: Any,
        event_bus: Any,
        log_root: str | Path,
        pending_ttl_sec: float = 300.0,
        pending_max_entries: int = 512,
        on_runtime_result_observed: Any | None = None,
        state_store: Any | None = None,
    ) -> None:
        self.state = state
        self.state_store = state_store
        self.event_bus = event_bus
        self.artifacts = GatewayArtifactResolver(log_root)
        self.pending_results = PendingCorrelationStore(ttl_sec=pending_ttl_sec, max_entries=pending_max_entries)
        self.pending_decisions = PendingCorrelationStore(ttl_sec=pending_ttl_sec, max_entries=pending_max_entries)
        self.on_runtime_result_observed = on_runtime_result_observed

    def _mutate_state(self, mutator: Callable[[Any], Any]) -> Any:
        if self.state_store is not None:
            return self.state_store.mutate(mutator)
        mutator(self.state)
        return deepcopy(self.state)

    def _read_state(self, reader: Callable[[Any], Any]) -> Any:
        if self.state_store is not None:
            return self.state_store.read(reader)
        return reader(self.state)

    def _snapshot_payload(self) -> dict[str, Any]:
        if self.state_store is not None:
            return self.state_store.snapshot_payload()
        return self.state.snapshot_payload()

    def _stats_payload(self) -> dict[str, Any]:
        if self.state_store is not None:
            return self.state_store.stats_payload()
        return self.state.stats_payload()

    def on_count_stats(self, msg: CountStats) -> None:
        def _apply(state: Any) -> None:
            state.absolute_stats = {
                'total': float(msg.total_count),
                'ok': float(msg.ok_count),
                'ng': float(msg.ng_count),
                'recheck': float(msg.recheck_count),
                'yieldRate': float(msg.yield_rate),
                'avgCycleMs': float(msg.avg_cycle_time_sec) * 1000.0,
            }
            state.last_updated_at = utc_now()

        self._mutate_state(_apply)
        self.event_bus.broadcast('station.count.updated', self._stats_payload())
        self._touch_heartbeat('STM32', 'ONLINE', 50.0)

    def on_station_state(self, msg: StationState) -> None:
        detail = safe_json_loads(msg.detail or '{}')
        mapped_phase = normalize_phase(msg.state)

        def _apply(state: Any) -> None:
            if mapped_phase != 'IDLE' or state.phase in {'BOOT', 'IDLE'}:
                state.phase = mapped_phase
            state.mode = normalize_mode(state.phase, detail)
            if msg.batch_id:
                state.batch_id = msg.batch_id
            state.guidance = self._guidance_from_state(msg.state, detail)
            state.last_updated_at = ros_time_to_iso(msg.stamp)
            raw_mode = str(detail.get('mode', '')).upper()
            if raw_mode in {'MAINTENANCE', 'MANUAL'}:
                state.maintenance_requested = True
                state.maintenance_active = True
                state.maintenance_transition_state = 'ENABLED'

        self._mutate_state(_apply)
        self.event_bus.broadcast('station.state.updated', self._snapshot_payload())
        self._touch_heartbeat('STM32', 'DEGRADED' if msg.state == 'HEARTBEAT_LOST' else 'ONLINE', 30.0)

    def on_result(self, msg: InspectionResult) -> None:
        detail = safe_json_loads(msg.detail_json or '{}')
        trace_id = str(detail.get('trace_id', f'{msg.batch_id}-{msg.item_id:05d}'))
        recipe_name = self._read_state(lambda state: str(state.active_recipe_name))
        record = {
            'id': trace_id,
            'timestamp': ros_time_to_iso(msg.stamp),
            'batchId': msg.batch_id,
            'recipeId': msg.recipe_id,
            'recipeName': recipe_name,
            'category': msg.category,
            'defectType': msg.defect_type,
            'qrText': msg.qr_text,
            'metricValue': _safe_float(msg.score, default=0.0),
            'metricLabel': 'score',
            'imageUrl': self.artifacts.artifact_url(msg.image_path),
            'overlayUrl': self.artifacts.artifact_url(msg.annotated_image_path),
            'cycleMs': _safe_float(detail.get('processing_ms', 0.0), default=0.0),
            'explanation': [str(item) for item in detail.get('warnings', [])] if isinstance(detail.get('warnings', []), list) else [],
            'breakdown': {
                'feedingMs': 0.0,
                'captureMs': 0.0,
                'analyzeMs': _safe_float(detail.get('processing_ms', 0.0), default=0.0),
                'sortingMs': 0.0,
                'totalMs': _safe_float(detail.get('processing_ms', 0.0), default=0.0),
            },
        }

        def _apply(state: Any) -> None:
            state.latest_frame = {
                'url': record['overlayUrl'] or record['imageUrl'],
                'capturedAt': record['timestamp'],
                'annotated': bool(record['overlayUrl']),
                'semantic': 'LATEST_RESULT_FRAME',
                'sourceEvent': 'inspection.result.created',
                'description': '最近一次视觉处理结果对应的图像快照。',
            }

        snapshot = self._mutate_state(_apply)
        self.event_bus.broadcast('camera.frame', snapshot.latest_frame)
        self.pending_results.put(trace_id, record)
        if callable(self.on_runtime_result_observed):
            try:
                self.on_runtime_result_observed(
                    {
                        'traceId': trace_id,
                        'recipeId': str(msg.recipe_id),
                        'batchId': str(msg.batch_id),
                        'timestamp': record['timestamp'],
                        'recipeVersion': str(detail.get('recipe_version', '')),
                    }
                )
            except Exception:
                pass
        self._emit_result_if_ready(trace_id)
        self._touch_heartbeat('ROS2', 'ONLINE', 20.0)

    def on_fault(self, msg: FaultEvent) -> None:
        payload = {
            'id': str(uuid.uuid4()),
            'code': msg.fault_code,
            'level': msg.level or 'ERROR',
            'message': msg.description,
            'timestamp': ros_time_to_iso(msg.stamp),
            'recoverable': bool(msg.recoverable),
            'suggestion': '请检查桥接链路、相机缓存与当前工位状态。',
        }

        def _apply(state: Any) -> None:
            state.phase = 'FAULT'
            state.mode = 'FAULT'
            state.guidance = f'故障：{msg.fault_code}'
            state.latest_fault = payload
            state.last_updated_at = payload['timestamp']

        self._mutate_state(_apply)
        self.event_bus.broadcast('fault.raised', payload)
        self.event_bus.broadcast('station.state.updated', self._snapshot_payload())
        self._touch_heartbeat('STM32', 'DEGRADED', 100.0)

    def on_event(self, msg_data: str) -> None:
        payload = safe_json_loads(msg_data)
        event_type = str(payload.get('type', ''))
        if event_type == 'fsm_transition':
            raw_target_phase = str(payload.get('to_phase', payload.get('phase', ''))).upper()
            from_phase = str(payload.get('from_phase', '')).upper()

            def _apply_transition(state: Any) -> None:
                target_phase = normalize_phase(raw_target_phase or state.phase)
                state.phase = target_phase
                state.mode = normalize_mode(target_phase, payload)
                state.cycle_index = _safe_int(payload.get('cycle_index', state.cycle_index), default=state.cycle_index)
                state.guidance = self._guidance_from_phase(raw_target_phase or target_phase)
                state.last_updated_at = str(payload.get('time', utc_now()))
                manual_enabled = bool(payload.get('manual_mode_enabled', False))
                if raw_target_phase == 'MANUAL_MODE' or manual_enabled:
                    state.maintenance_requested = True
                    state.maintenance_active = True
                    state.maintenance_transition_state = 'ENABLED'
                    current_supervisor_mode = str(getattr(state, 'supervisor_mode', '')).strip()
                    state.supervisor_mode = 'MAINTENANCE' if not current_supervisor_mode else current_supervisor_mode
                    if state.mode == 'IDLE':
                        state.mode = 'DEBUG'
                elif from_phase == 'MANUAL_MODE' or bool(getattr(state, 'maintenance_active', False)):
                    state.maintenance_active = False
                    if not bool(getattr(state, 'maintenance_requested', False)):
                        state.maintenance_transition_state = 'LOCKED'
                    elif str(getattr(state, 'maintenance_transition_state', '')) == 'EXITING':
                        state.maintenance_transition_state = 'LOCKED'
                    if state.mode == 'DEBUG':
                        state.mode = normalize_mode(target_phase, payload)

            self._mutate_state(_apply_transition)
            self.event_bus.broadcast('station.state.updated', self._snapshot_payload())
        elif event_type == 'cycle_started':
            def _apply_cycle_started(state: Any) -> None:
                state.mode = 'AUTO'
                state.guidance = '工位已启动，正在执行自动节拍。'
                state.cycle_index = _safe_int(payload.get('cycle_index', state.cycle_index), default=state.cycle_index)
                state.last_updated_at = str(payload.get('time', utc_now()))

            self._mutate_state(_apply_cycle_started)
            self.event_bus.broadcast('station.state.updated', self._snapshot_payload())
        elif event_type == 'cycle_finish':
            self._mutate_state(lambda state: setattr(state, 'continuous_run_count', state.continuous_run_count + 1))
        elif event_type == 'fault_raised':
            code = str(payload.get('code', 'FAULT'))

            def _apply_fault_event(state: Any) -> None:
                state.phase = 'FAULT'
                state.mode = 'FAULT'
                state.guidance = f'故障：{code}'
                state.last_updated_at = str(payload.get('time', utc_now()))
                if str(getattr(state, 'maintenance_transition_state', '')) == 'ENTERING':
                    state.maintenance_transition_state = 'LOCKED'
                    state.maintenance_requested = False
                    state.maintenance_active = False

            self._mutate_state(_apply_fault_event)
            self.event_bus.broadcast('station.state.updated', self._snapshot_payload())
        elif event_type == 'decision_published':
            trace_id = str(payload.get('trace_id', ''))
            if trace_id:
                self.pending_decisions.put(trace_id, dict(payload))
                self._emit_result_if_ready(trace_id)
        elif event_type == 'bridge_heartbeat':
            self._touch_heartbeat('STM32', 'ONLINE', 10.0, timestamp=str(payload.get('time', utc_now())))
        elif event_type == 'vision_capture_done':
            self._touch_heartbeat('ESP32-S3', 'ONLINE', _safe_float(payload.get('processing_ms', 0.0), default=0.0), timestamp=str(payload.get('time', utc_now())))

        elif event_type == 'supervisor_state':
            mode_payload = payload.get('mode', {}) if isinstance(payload.get('mode', {}), dict) else {}
            current_mode = str(mode_payload.get('current_mode', payload.get('current_mode', ''))).upper()

            def _apply_supervisor_state(state: Any) -> None:
                if current_mode:
                    setattr(state, 'supervisor_mode', current_mode)
                state.last_updated_at = str(payload.get('time', utc_now()))
                if current_mode == 'MAINTENANCE':
                    state.maintenance_requested = True
                    if not bool(getattr(state, 'maintenance_active', False)):
                        state.maintenance_transition_state = 'ENTERING'
                elif current_mode in {'AUTO', 'PAUSED', 'STOPPED', 'BENCHMARK'}:
                    state.maintenance_requested = False
                    if bool(getattr(state, 'maintenance_active', False)):
                        state.maintenance_transition_state = 'EXITING'
                    else:
                        state.maintenance_transition_state = 'LOCKED'

            self._mutate_state(_apply_supervisor_state)
            self.event_bus.broadcast('station.state.updated', self._snapshot_payload())


    def on_orchestrator_advice(self, msg_data: str) -> None:
        """Project orchestrator advice into gateway events and cached state.

        Args:
            msg_data: JSON payload emitted by ``/inspection/orchestrator/advice``.

        Returns:
            None.

        Boundary behavior:
            Advice remains observational by default; this handler surfaces it to
            the HMI without turning advisory output into implicit control.
        """
        payload = safe_json_loads(msg_data)
        actions = payload.get('actions', []) if isinstance(payload.get('actions', []), list) else []
        normalized = {
            'node': str(payload.get('node', 'inspection_orchestrator_node')),
            'tree': str(payload.get('tree', '')),
            'status': str(payload.get('status', 'UNKNOWN')),
            'durationMs': _safe_int(payload.get('durationMs', 0), default=0),
            'time': str(payload.get('time', utc_now())),
            'actions': [dict(item) for item in actions if isinstance(item, dict)],
            'trace': payload.get('trace') if isinstance(payload.get('trace'), (dict, list)) else payload.get('trace'),
        }
        self._mutate_state(lambda state: setattr(state, 'latest_orchestrator_advice', dict(normalized)))
        self.event_bus.broadcast('orchestrator.advice', normalized)

    def on_diagnostics(self, msg_data: str) -> None:
        payload = safe_json_loads(msg_data)
        channels = payload.get('channels', {}) if isinstance(payload.get('channels', {}), dict) else {}
        items: list[dict[str, Any]] = []
        for name, data in sorted(channels.items()):
            if not isinstance(data, dict):
                continue
            values = data.get('values', {}) if isinstance(data.get('values', {}), dict) else {}
            summary_values = ', '.join(f'{k}={v}' for k, v in list(values.items())[:3])
            items.append(
                {
                    'id': str(name),
                    'name': str(name),
                    'value': summary_values or str(data.get('level', 'OK')),
                    'status': to_health(str(data.get('level', 'OK'))),
                    'note': str(data.get('message', '')),
                }
            )
        self._mutate_state(lambda state: setattr(state, 'diagnostics', items))

    def artifact_url(self, path: str | Path) -> str:
        return self.artifacts.artifact_url(path)

    def _touch_heartbeat(self, source: str, status: str, latency_ms: float, *, timestamp: str | None = None) -> None:
        payload = {
            'source': source,
            'status': status,
            'latencyMs': round(float(latency_ms), 3),
            'timestamp': timestamp or utc_now(),
        }

        def _apply(state: Any) -> None:
            state.heartbeats[source] = payload

        self._mutate_state(_apply)
        self.event_bus.broadcast('system.heartbeat', payload)

    def _emit_result_if_ready(self, trace_id: str) -> None:
        result = self.pending_results.get(trace_id)
        if result is None:
            return
        decision_payload = self.pending_decisions.get(trace_id)
        if decision_payload is None:
            return
        explanation = list(result.get('explanation', []))
        reason = decision_payload.get('reason')
        if reason:
            explanation.append(str(reason))
        if isinstance(decision_payload.get('explanation', []), list):
            explanation.extend(str(item) for item in decision_payload.get('explanation', []) if item)
        record = {
            **result,
            'decision': str(decision_payload.get('decision', 'RECHECK')),
            'explanation': explanation or ['判定已生成'],
        }
        self.event_bus.broadcast('inspection.result.created', record)
        self.pending_results.pop(trace_id)
        self.pending_decisions.pop(trace_id)

    def _guidance_from_phase(self, phase: str) -> str:
        phase_key = str(phase).upper()
        mapping = {
            'BOOT': '系统自检中。',
            'IDLE': '等待启动命令。',
            'READY': '工位待命，可开始新节拍。',
            'FEEDING': '正在请求上料。',
            'POSITION_CHECK': '正在确认到位状态。',
            'CAPTURE': '正在抓取图像。',
            'ANALYZE': '正在执行视觉判定。',
            'SORTING': '正在执行分拣动作。',
            'COUNT_UPDATE': '正在刷新统计。',
            'MANUAL_MODE': '维护模式已生效，可执行手动单步动作。',
            'FAULT': '系统故障，等待人工干预。',
        }
        return mapping.get(phase_key, '状态更新中。')

    def _guidance_from_state(self, state_name: str, detail: dict[str, Any]) -> str:
        state_name = str(state_name).upper()
        if state_name == 'HEARTBEAT':
            return '设备心跳正常。'
        if state_name == 'HEARTBEAT_LOST':
            return '设备心跳丢失，请检查链路。'
        if state_name == 'FAULT':
            return f"设备故障：{detail.get('fault_code', 'FAULT')}"
        return self._guidance_from_phase(normalize_phase(state_name))
