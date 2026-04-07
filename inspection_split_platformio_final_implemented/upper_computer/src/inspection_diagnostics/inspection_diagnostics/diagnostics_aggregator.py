from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from inspection_utils.lifecycle_matrix import lifecycle_governance_matrix
from inspection_utils.qos import qos_compatibility_warnings, qos_policy_matrix

from .diagnostic_rules import finalize_snapshot
from .health_model import DiagnosticsSnapshot


@dataclass(slots=True)
class DiagnosticsAggregator:
    vision_processing_ms: list[float] = field(default_factory=list)
    last_station_detail: dict[str, Any] = field(default_factory=dict)
    recent_faults: list[str] = field(default_factory=list)
    last_bridge_session: dict[str, Any] = field(default_factory=dict)
    last_control_mode: str = 'AUTO'
    bag_recording: dict[str, Any] = field(default_factory=dict)
    lifecycle_plan: list[dict[str, Any]] = field(default_factory=list)
    next_lifecycle_command: dict[str, Any] = field(default_factory=dict)
    last_vision_budget: dict[str, Any] = field(default_factory=dict)
    last_artifact_writer: dict[str, Any] = field(default_factory=dict)

    def ingest_event(self, event: dict[str, Any]) -> None:
        """Consume structured runtime events emitted by the station."""
        event_type = str(event.get('type', ''))
        if event_type == 'vision_capture_done':
            try:
                self.vision_processing_ms.append(float(event.get('processing_ms', 0.0)))
            except Exception:
                pass
            self.vision_processing_ms = self.vision_processing_ms[-50:]
            budget = event.get('latency_budget', {}) if isinstance(event.get('latency_budget', {}), dict) else {}
            if budget:
                self.last_vision_budget = dict(budget)
            artifact_writer = event.get('artifact_writer', {}) if isinstance(event.get('artifact_writer', {}), dict) else {}
            if artifact_writer:
                self.last_artifact_writer = dict(artifact_writer)
        elif event_type == 'fault':
            code = str(event.get('code', event.get('fault_code', 'UNKNOWN_FAULT')))
            self.recent_faults.append(code)
            self.recent_faults = self.recent_faults[-20:]
        elif event_type == 'supervisor_state':
            mode = event.get('mode', {})
            if isinstance(mode, dict):
                self.last_control_mode = str(mode.get('current_mode', self.last_control_mode))
            plan = event.get('lifecycle_plan', [])
            if isinstance(plan, list):
                self.lifecycle_plan = [item for item in plan if isinstance(item, dict)]
            next_cmd = event.get('next_lifecycle_command', {})
            if isinstance(next_cmd, dict):
                self.next_lifecycle_command = dict(next_cmd)
        elif event_type == 'lifecycle_command':
            self.next_lifecycle_command = {
                'signature': str(event.get('signature', '')),
                'node': str(event.get('node', '')),
                'transition': str(event.get('transition', '')),
            }
        elif event_type == 'bag_recording_started':
            self.bag_recording = {
                'enabled': bool(event.get('enabled', False)),
                'output_path': str(event.get('output_path', '')),
                'topics': list(event.get('topics', [])) if isinstance(event.get('topics', []), list) else [],
            }

    def ingest_station_state(self, detail: dict[str, Any]) -> None:
        """Consume station state detail from the device bridge."""
        self.last_station_detail = dict(detail)
        session = detail.get('session')
        if isinstance(session, dict):
            self.last_bridge_session = dict(session)

    def build_snapshot(self) -> dict[str, Any]:
        """Build the aggregated diagnostics snapshot."""
        snapshot = DiagnosticsSnapshot()
        avg_processing = round(sum(self.vision_processing_ms) / len(self.vision_processing_ms), 3) if self.vision_processing_ms else 0.0
        vision_level = 'WARN' if avg_processing > 400.0 else 'OK'
        snapshot.set_channel('vision', vision_level, 'processing latency tracked', avg_processing_ms=avg_processing, sample_count=len(self.vision_processing_ms))

        budget_level = self._vision_budget_level()
        snapshot.set_channel('vision_budget', budget_level, 'vision latency budget state', **dict(self.last_vision_budget))

        writer_level = self._artifact_backpressure_level()
        snapshot.set_channel('artifact_backpressure', writer_level, 'artifact writer backpressure state', **dict(self.last_artifact_writer))

        bridge_phase = str(self.last_bridge_session.get('phase', self.last_station_detail.get('session_phase', 'UNKNOWN')))
        heartbeat_ok = bool(self.last_station_detail.get('heartbeat_ok', True))
        bridge_level = 'ERROR' if not heartbeat_ok else ('WARN' if bridge_phase in {'DEGRADED', 'RECONNECTING'} else 'OK')
        snapshot.set_channel('bridge', bridge_level, 'bridge session state', phase=bridge_phase, heartbeat_ok=heartbeat_ok, session=self.last_bridge_session)

        fault_level = 'WARN' if self.recent_faults else 'OK'
        snapshot.set_channel('faults', fault_level, 'recent fault backlog', count=len(self.recent_faults), recent_faults=list(self.recent_faults[-10:]))
        snapshot.set_channel('control_mode', 'OK', 'supervisor mode observed', mode=self.last_control_mode)

        bag_enabled = bool(self.bag_recording.get('enabled', False))
        snapshot.set_channel('bag_recording', 'OK' if bag_enabled else 'WARN', 'rosbag recording state', **dict(self.bag_recording))
        snapshot.set_channel('lifecycle_plan', 'OK', 'supervisor lifecycle guidance', pending=list(self.lifecycle_plan[:8]), next_command=dict(self.next_lifecycle_command))
        snapshot.set_channel('lifecycle_governance', 'OK', 'lifecycle governance matrix', matrix=lifecycle_governance_matrix())
        snapshot.set_channel(
            'qos_governance',
            'OK',
            'declared qos matrix and compatibility heuristics',
            matrix=qos_policy_matrix(),
            warnings=qos_compatibility_warnings(publisher='sensor_data', subscriber='result'),
        )
        return finalize_snapshot(snapshot).to_dict()

    def _vision_budget_level(self) -> str:
        exceeded = bool(self.last_vision_budget.get('exceeded', False))
        return 'WARN' if exceeded else 'OK'

    def _artifact_backpressure_level(self) -> str:
        queue_usage = float(self.last_artifact_writer.get('queueUsage', 0.0) or 0.0)
        flush_timeouts = int(self.last_artifact_writer.get('flushTimeouts', 0) or 0)
        failed = int(self.last_artifact_writer.get('failed', 0) or 0)
        dropped = int(self.last_artifact_writer.get('droppedOverload', 0) or 0)
        if failed > 0 or flush_timeouts > 0:
            return 'ERROR'
        if dropped > 0 or queue_usage >= 0.8:
            return 'WARN'
        return 'OK'
