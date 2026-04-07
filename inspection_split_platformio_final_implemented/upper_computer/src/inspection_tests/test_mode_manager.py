from __future__ import annotations

from inspection_supervisor.mode_manager import ModeManager, SupervisorMode


def test_mode_manager_tracks_history() -> None:
    manager = ModeManager()
    assert manager.request('auto', reason='boot') is True
    assert manager.request(SupervisorMode.MAINTENANCE, reason='operator') is True
    snap = manager.snapshot()
    assert snap['current_mode'] == 'MAINTENANCE'
    assert snap['history'][-1]['reason'] == 'operator'
    assert manager.is_manual_like() is True
