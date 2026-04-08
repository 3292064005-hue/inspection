import time

from inspection_orchestrator.bt import Action, CANCELLED, Condition, Selector, Sequence, TIMEOUT, build_node_from_spec
from inspection_orchestrator.task_tree.auto_run_tree import plan_auto_run
from inspection_orchestrator.tree_runtime import OrchestratorTreeRuntime


def test_bt_sequence_and_selector_produce_expected_actions():
    tree = Selector(
        'root',
        Sequence(
            'healthy_path',
            Condition('healthy', lambda ctx: bool(ctx['healthy'])),
            Action('resume', lambda _ctx: [{'action': 'resume'}]),
        ),
        Action('pause', lambda _ctx: [{'action': 'pause'}]),
    )
    assert tree.evaluate({'healthy': True}).actions == [{'action': 'resume'}]
    assert tree.evaluate({'healthy': False}).actions == [{'action': 'pause'}]


def test_bt_honors_cancel_before_node_execution() -> None:
    tree = Sequence(
        'root',
        Condition('always', lambda _ctx: True),
        Action('resume', lambda _ctx: [{'action': 'resume'}]),
    )
    result = tree.evaluate({'__cancel_requested__': True})
    assert result.status == CANCELLED
    assert result.actions == []


def test_bt_honors_deadline_timeout() -> None:
    tree = build_node_from_spec({
        'type': 'action',
        'label': 'slow_action',
        'actions': [{'action': 'noop'}],
    })
    result = tree.evaluate({'__deadline_monotonic__': time.perf_counter() - 0.001})
    assert result.status == TIMEOUT


def test_tree_runtime_loads_external_catalog(tmp_path) -> None:
    config = tmp_path / 'orchestrator_trees.yaml'
    config.write_text(
        '''version: 1\nroot_timeout_ms: 25\ntrees:\n  startup:\n    type: action\n    label: startup\n    actions:\n      - action: start_auto_cycle\n  auto_run:\n    type: action\n    label: auto_run\n    actions:\n      - action: resume\n  benchmark:\n    type: action\n    label: benchmark\n    actions:\n      - action: pause\n  maintenance:\n    type: action\n    label: maintenance\n    actions:\n      - action: enter_manual\n  recovery:\n    type: action\n    label: recovery\n    actions:\n      - action: reset_fault\n''',
        encoding='utf-8',
    )
    runtime = OrchestratorTreeRuntime(str(config))
    plan = runtime.evaluate('startup', {'healthy': True})
    assert plan.actions == [{'action': 'start_auto_cycle'}]
    assert plan.status == 'SUCCESS'


def test_auto_run_plan_exposes_status_and_trace() -> None:
    plan = plan_auto_run({'health': {'healthy': True}}, {'overall_level': 'WARN'})
    assert plan.status == 'SUCCESS'
    assert plan.actions == [{'action': 'pause', 'reason': 'diagnostics_warn'}]
    assert any('warn_pause' in item for item in plan.trace)
