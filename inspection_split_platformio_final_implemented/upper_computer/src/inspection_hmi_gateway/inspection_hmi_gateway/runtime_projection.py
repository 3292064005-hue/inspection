from __future__ import annotations

"""Projection and artifact helpers for the gateway runtime."""

from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Any
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
    ) -> None:
        self.state = state
        self.event_bus = event_bus
        self.artifacts = GatewayArtifactResolver(log_root)
        self.pending_results = PendingCorrelationStore(ttl_sec=pending_ttl_sec, max_entries=pending_max_entries)
        self.pending_decisions = PendingCorrelationStore(ttl_sec=pending_ttl_sec, max_entries=pending_max_entries)
        self.on_runtime_result_observed = on_runtime_result_observed

    def on_count_stats(self, msg: CountStats) -> None:
        self.state.absolute_stats = {
            'total': float(msg.total_count),
            'ok': float(msg.ok_count),
            'ng': float(msg.ng_count),
            'recheck': float(msg.recheck_count),
            'yieldRate': float(msg.yield_rate),
            'avgCycleMs': float(msg.avg_cycle_time_sec) * 1000.0,
        }
        self.state.last_updated_at = utc_now()
        self.event_bus.broadcast('station.count.updated', self.state.stats_payload())
        self._touch_heartbeat('STM32', 'ONLINE', 50.0)

    def on_station_state(self, msg: StationState) -> None:
        detail = safe_json_loads(msg.detail or '{}')
        mapped_phase = normalize_phase(msg.state)
        if mapped_phase != 'IDLE' or self.state.phase in {'BOOT', 'IDLE'}:
            self.state.phase = mapped_phase
        self.state.mode = normalize_mode(self.state.phase, detail)
        if msg.batch_id:
            self.state.batch_id = msg.batch_id
        self.state.guidance = self._guidance_from_state(msg.state, detail)
        self.state.last_updated_at = ros_time_to_iso(msg.stamp)
        self.event_bus.broadcast('station.state.updated', self.state.snapshot_payload())
        self._touch_heartbeat('STM32', 'DEGRADED' if msg.state == 'HEARTBEAT_LOST' else 'ONLINE', 30.0)

    def on_result(self, msg: InspectionResult) -> None:
        detail = safe_json_loads(msg.detail_json or '{}')
        trace_id = str(detail.get('trace_id', f'{msg.batch_id}-{msg.item_id:05d}'))
        record = {
            'id': trace_id,
            'timestamp': ros_time_to_iso(msg.stamp),
            'batchId': msg.batch_id,
            'recipeId': msg.recipe_id,
            'recipeName': self.state.active_recipe_name,
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
        self.state.latest_frame = {
            'url': record['overlayUrl'] or record['imageUrl'],
            'capturedAt': record['timestamp'],
            'annotated': bool(record['overlayUrl']),
        }
        self.event_bus.broadcast('camera.frame', self.state.latest_frame)
        self.pending_results.put(trace_id, record)
        if callable(self.on_runtime_result_observed):
            try:
                self.on_runtime_result_observed({
                    'traceId': trace_id,
                    'recipeId': str(msg.recipe_id),
                    'batchId': str(msg.batch_id),
                    'timestamp': record['timestamp'],
                    'recipeVersion': str(detail.get('recipe_version', '')),
                })
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
        self.state.phase = 'FAULT'
        self.state.mode = 'FAULT'
        self.state.guidance = f'故障：{msg.fault_code}'
        self.state.latest_fault = payload
        self.state.last_updated_at = payload['timestamp']
        self.event_bus.broadcast('fault.raised', payload)
        self.event_bus.broadcast('station.state.updated', self.state.snapshot_payload())
        self._touch_heartbeat('STM32', 'DEGRADED', 100.0)

    def on_event(self, msg_data: str) -> None:
        payload = safe_json_loads(msg_data)
        event_type = str(payload.get('type', ''))
        if event_type == 'fsm_transition':
            target_phase = normalize_phase(str(payload.get('to_phase', payload.get('phase', self.state.phase))))
            self.state.phase = target_phase
            self.state.mode = normalize_mode(target_phase, payload)
            self.state.cycle_index = _safe_int(payload.get('cycle_index', self.state.cycle_index), default=self.state.cycle_index)
            self.state.guidance = self._guidance_from_phase(target_phase)
            self.state.last_updated_at = str(payload.get('time', utc_now()))
            self.event_bus.broadcast('station.state.updated', self.state.snapshot_payload())
        elif event_type == 'cycle_started':
            self.state.mode = 'AUTO'
            self.state.guidance = '工位已启动，正在执行自动节拍。'
            self.state.cycle_index = _safe_int(payload.get('cycle_index', self.state.cycle_index), default=self.state.cycle_index)
            self.state.last_updated_at = str(payload.get('time', utc_now()))
            self.event_bus.broadcast('station.state.updated', self.state.snapshot_payload())
        elif event_type == 'cycle_finish':
            self.state.continuous_run_count += 1
        elif event_type == 'fault_raised':
            code = str(payload.get('code', 'FAULT'))
            self.state.phase = 'FAULT'
            self.state.mode = 'FAULT'
            self.state.guidance = f'故障：{code}'
            self.state.last_updated_at = str(payload.get('time', utc_now()))
            self.event_bus.broadcast('station.state.updated', self.state.snapshot_payload())
        elif event_type == 'decision_published':
            trace_id = str(payload.get('trace_id', ''))
            if trace_id:
                self.pending_decisions.put(trace_id, dict(payload))
                self._emit_result_if_ready(trace_id)
        elif event_type == 'bridge_heartbeat':
            self._touch_heartbeat('STM32', 'ONLINE', 10.0, timestamp=str(payload.get('time', utc_now())))
        elif event_type == 'vision_capture_done':
            self._touch_heartbeat('ESP32-S3', 'ONLINE', _safe_float(payload.get('processing_ms', 0.0), default=0.0), timestamp=str(payload.get('time', utc_now())))

    def on_diagnostics(self, msg_data: str) -> None:
        payload = safe_json_loads(msg_data)
        channels = payload.get('channels', {}) if isinstance(payload.get('channels', {}), dict) else {}
        items: list[dict[str, Any]] = []
        for name, data in sorted(channels.items()):
            if not isinstance(data, dict):
                continue
            values = data.get('values', {}) if isinstance(data.get('values', {}), dict) else {}
            summary_values = ', '.join(f'{k}={v}' for k, v in list(values.items())[:3])
            items.append({
                'id': str(name),
                'name': str(name),
                'value': summary_values or str(data.get('level', 'OK')),
                'status': to_health(str(data.get('level', 'OK'))),
                'note': str(data.get('message', '')),
            })
        self.state.diagnostics = items

    def artifact_url(self, path: str | Path) -> str:
        return self.artifacts.artifact_url(path)

    def _touch_heartbeat(self, source: str, status: str, latency_ms: float, *, timestamp: str | None = None) -> None:
        payload = {
            'source': source,
            'status': status,
            'latencyMs': round(float(latency_ms), 3),
            'timestamp': timestamp or utc_now(),
        }
        self.state.heartbeats[source] = payload
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
            'FAULT': '系统故障，等待人工干预。',
        }
        return mapping.get(phase, '状态更新中。')

    def _guidance_from_state(self, state_name: str, detail: dict[str, Any]) -> str:
        state_name = str(state_name).upper()
        if state_name == 'HEARTBEAT':
            return '设备心跳正常。'
        if state_name == 'HEARTBEAT_LOST':
            return '设备心跳丢失，请检查链路。'
        if state_name == 'FAULT':
            return f"设备故障：{detail.get('fault_code', 'FAULT')}"
        return self._guidance_from_phase(normalize_phase(state_name))
