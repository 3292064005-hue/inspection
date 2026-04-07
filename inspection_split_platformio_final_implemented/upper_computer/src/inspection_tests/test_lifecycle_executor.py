from inspection_supervisor.lifecycle_executor import LifecycleExecutor
from inspection_supervisor.lifecycle_clients import lifecycle_command_from_plan_item
from inspection_supervisor.lifecycle_manager import LifecycleManager
from inspection_supervisor.node_health_registry import NodeHealthRegistry


def test_lifecycle_command_from_plan_item_maps_activate():
    cmd = lifecycle_command_from_plan_item({'action': 'activate_node', 'node': 'vision_processor_node', 'reason': 'start'})
    assert cmd is not None
    assert cmd.transition == 'ACTIVATE'
    assert cmd.target_state == 'ACTIVE'
    assert cmd.signature == 'vision_processor_node:ACTIVATE:ACTIVE'


def test_lifecycle_executor_deduplicates_last_signature():
    executor = LifecycleExecutor()
    plan = [{'action': 'configure_node', 'node': 'camera_node'}]
    first = executor.next_command(plan)
    assert first is not None
    executor.mark_dispatched(first)
    assert executor.next_command(plan) is None


def test_lifecycle_manager_exposes_next_command():
    registry = NodeHealthRegistry(
        expected_nodes=['camera_node'],
        required_nodes={'camera_node'},
        node_classes={'camera_node': 'required'},
    )
    registry.ingest_event('camera_node', now=1.0, event_type='evt', state='INACTIVE')
    manager = LifecycleManager(['camera_node'])
    result = manager.evaluate(registry, now=1.5, timeout_sec=5.0, mode='AUTO')
    assert result['next_lifecycle_command']['transition'] == 'ACTIVATE'
