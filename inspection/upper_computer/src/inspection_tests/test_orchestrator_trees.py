from __future__ import annotations

from inspection_orchestrator.task_tree.auto_run_tree import evaluate_auto_run
from inspection_orchestrator.task_tree.maintenance_tree import evaluate_maintenance
from inspection_orchestrator.task_tree.startup_tree import evaluate_startup


def test_startup_tree_waits_until_stack_healthy() -> None:
    actions = evaluate_startup({'health': {'healthy': False}})
    assert actions == [{'action': 'await_health'}]


def test_auto_run_tree_requests_recovery_on_error() -> None:
    actions = evaluate_auto_run({'health': {'healthy': True}}, {'overall_level': 'ERROR'})
    assert actions[0]['action'] == 'pause'
    assert actions[1]['action'] == 'request_recovery'


def test_maintenance_tree_enters_manual() -> None:
    actions = evaluate_maintenance({'mode': {'current_mode': 'MAINTENANCE'}})
    assert actions == [{'action': 'enter_manual'}]
