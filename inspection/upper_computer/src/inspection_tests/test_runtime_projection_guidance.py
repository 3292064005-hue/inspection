from __future__ import annotations

from pathlib import Path

from inspection_hmi_gateway.runtime_components import GatewayReadModelProjector


class _Bus:
    def __init__(self) -> None:
        self.messages: list[tuple[str, dict]] = []

    def broadcast(self, event: str, payload: dict) -> None:
        self.messages.append((event, payload))


class _State:
    def __init__(self) -> None:
        self.phase = 'BOOT'
        self.mode = 'IDLE'
        self.batch_id = 'BATCH-1'
        self.active_recipe_name = '配方'
        self.active_recipe_id = 'recipe-1'
        self.cycle_index = 0
        self.guidance = ''
        self.last_updated_at = ''
        self.absolute_stats = {'total': 0.0, 'ok': 0.0, 'ng': 0.0, 'recheck': 0.0, 'yieldRate': 0.0, 'avgCycleMs': 0.0}
        self.batch_baseline = {'total': 0.0, 'ok': 0.0, 'ng': 0.0, 'recheck': 0.0}
        self.continuous_run_count = 0
        self.latest_frame = {'url': '', 'capturedAt': '', 'annotated': False, 'semantic': 'LATEST_RESULT_FRAME', 'sourceEvent': 'inspection.result.observed', 'description': ''}
        self.latest_fault = None
        self.diagnostics = []
        self.heartbeats = {}

    def snapshot_payload(self) -> dict:
        return {'phase': self.phase, 'mode': self.mode, 'batchId': self.batch_id, 'activeRecipeName': self.active_recipe_name}

    def stats_payload(self) -> dict:
        return {'total': 0, 'ok': 0, 'ng': 0, 'recheck': 0, 'yieldRate': 0.0, 'continuousRunCount': 0, 'avgCycleMs': 0.0}


def test_fsm_transition_guidance_uses_normalized_phase_mapping(tmp_path: Path) -> None:
    logs_root = tmp_path / 'logs'
    logs_root.mkdir()
    state = _State()
    bus = _Bus()
    projector = GatewayReadModelProjector(state=state, event_bus=bus, log_root=logs_root)

    projector.on_event('{"type":"fsm_transition","to_phase":"DECISION_WAIT","time":"2026-01-01T00:00:00Z"}')

    assert state.phase == 'ANALYZE'
    assert state.guidance == '正在执行视觉判定。'
