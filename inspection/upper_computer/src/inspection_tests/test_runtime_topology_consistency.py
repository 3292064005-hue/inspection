from pathlib import Path

from inspection_supervisor.lifecycle_graph import load_runtime_topology, monitored_topology, ordered_monitored_startup, ordered_startup
from inspection_utils.lifecycle_matrix import lifecycle_governance_for


def test_runtime_topology_matches_launch_contracts() -> None:
    topology = load_runtime_topology()
    topology_names = {spec.name for spec in topology}
    root = Path(__file__).resolve().parents[2]
    real_launch = (root / 'src' / 'inspection_bringup' / 'launch' / 'real_station.launch.py').read_text(encoding='utf-8')
    gateway_launch = (root / 'src' / 'inspection_hmi_gateway' / 'launch' / 'hmi_gateway.launch.py').read_text(encoding='utf-8')

    for expected in ['inspection_action_executor_node', 'inspection_orchestrator_node', 'inspection_hmi_gateway_server']:
        assert expected in topology_names
        assert expected in real_launch or expected in gateway_launch

    gateway = next(spec for spec in topology if spec.name == 'inspection_hmi_gateway_server')
    assert gateway.lifecycle_managed is False
    assert gateway.supervisor_monitored is False
    assert lifecycle_governance_for('inspection_hmi_gateway_node')['lifecycleMode'] == 'external_service'


def test_supervisor_monitored_startup_is_subset_of_lifecycle_and_topology_orders() -> None:
    topology = load_runtime_topology()
    monitored_order = ordered_monitored_startup(topology)
    managed_order = ordered_startup(tuple(spec for spec in topology if spec.lifecycle_managed))
    assert monitored_order[: len(managed_order)] == managed_order
    assert all(spec.name not in monitored_order for spec in topology if not spec.supervisor_monitored)
    assert {spec.name for spec in monitored_topology()} == set(monitored_order)


def test_non_managed_runtime_nodes_do_not_install_managed_runtime_or_launch_params() -> None:
    root = Path(__file__).resolve().parents[2]
    gateway_runtime = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'gateway_runtime.py').read_text(encoding='utf-8')
    supervisor_node = (root / 'src' / 'inspection_supervisor' / 'inspection_supervisor' / 'supervisor_node.py').read_text(encoding='utf-8')
    real_launch = (root / 'src' / 'inspection_bringup' / 'launch' / 'real_station.launch.py').read_text(encoding='utf-8')
    offline_launch = (root / 'src' / 'inspection_bringup' / 'launch' / 'offline_replay.launch.py').read_text(encoding='utf-8')

    assert 'setup_managed_runtime' not in gateway_runtime
    assert 'setup_managed_runtime' not in supervisor_node
    assert 'class GatewayNode(ExternalServiceRuntimeMixin, StandardRuntimeNode):' in gateway_runtime
    assert "setup_external_runtime(node_name='inspection_hmi_gateway_server', initial_state='ACTIVE')" in gateway_runtime
    assert 'class SupervisorNode(ExternalServiceRuntimeMixin, StandardRuntimeNode):' in supervisor_node
    assert "setup_external_runtime(node_name='inspection_supervisor_node', initial_state='ACTIVE')" in supervisor_node
    assert "inspection_supervisor_node', parameters=[{'profile_name': profile_name, 'health_timeout_sec': supervisor_health_timeout_sec}]" in real_launch
    assert "inspection_supervisor_node', parameters=[{'profile_name': profile_name, 'autostart_mode': 'BENCHMARK'}]" in offline_launch
