from inspection_orchestrator.task_tree.benchmark_tree import evaluate_benchmark


def test_benchmark_tree_requires_healthy_stack():
    actions = evaluate_benchmark({'health': {'healthy': False}}, {'overall_level': 'OK'})
    assert actions[0]['action'] == 'pause'
