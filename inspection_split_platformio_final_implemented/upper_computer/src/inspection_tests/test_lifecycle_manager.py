from inspection_supervisor.lifecycle_manager import LifecycleManager
from inspection_supervisor.node_health_registry import NodeHealthRegistry


def test_lifecycle_manager_requests_configure_for_unconfigured_node():
    registry = NodeHealthRegistry(
        expected_nodes=['station_bridge_node', 'camera_node'],
        required_nodes={'station_bridge_node', 'camera_node'},
        node_classes={'station_bridge_node': 'critical', 'camera_node': 'required'},
    )
    registry.ingest_event('station_bridge_node', now=1.0, event_type='evt', state='INACTIVE')
    registry.ingest_event('camera_node', now=1.0, event_type='evt', state='ACTIVE')
    manager = LifecycleManager(['station_bridge_node', 'camera_node'])
    plan = manager.evaluate(registry, now=1.5, timeout_sec=5.0, mode='AUTO')['lifecycle_plan']
    assert plan[0]['action'] == 'activate_node'
    assert plan[0]['node'] == 'station_bridge_node'
