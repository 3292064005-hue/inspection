from __future__ import annotations

from inspection_supervisor.recovery_policy import build_recovery_plan


def test_recovery_policy_prioritizes_pause_and_restart() -> None:
    plan = build_recovery_plan(
        healthy=False,
        stale_nodes=['station_bridge_node'],
        missing_active_nodes=['camera_node'],
        current_mode='AUTO',
    )
    actions = [step['action'] for step in plan]
    assert actions[:2] == ['pause_auto', 'restart_nodes']
    assert 'reactivate_nodes' in actions
    assert actions[-1] == 'request_reset_if_faulted'
