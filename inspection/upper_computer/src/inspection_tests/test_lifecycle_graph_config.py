from pathlib import Path

from inspection_supervisor.lifecycle_graph import load_lifecycle_graph, load_runtime_topology, monitored_topology, ordered_monitored_startup, ordered_startup


def test_lifecycle_graph_is_loaded_from_configuration() -> None:
    graph = load_lifecycle_graph()
    assert graph
    assert ordered_startup(graph)[0] == 'station_bridge_node'
    assert any(spec.name == 'inspection_diagnostics_node' and spec.required is False for spec in graph)


def test_runtime_topology_declares_managed_monitored_and_external_nodes() -> None:
    topology = load_runtime_topology()
    monitored = monitored_topology()
    assert any(spec.name == 'inspection_action_executor_node' and spec.lifecycle_managed and spec.supervisor_monitored for spec in topology)
    assert any(spec.name == 'inspection_orchestrator_node' and spec.lifecycle_managed and spec.supervisor_monitored for spec in topology)
    assert any(spec.name == 'inspection_hmi_gateway_server' and not spec.lifecycle_managed and not spec.supervisor_monitored for spec in topology)
    assert 'inspection_action_executor_node' in ordered_monitored_startup(topology)
    assert 'inspection_hmi_gateway_server' not in ordered_monitored_startup(topology)
    assert any(spec.fault_domain == 'gateway' for spec in topology)
    assert len(monitored) < len(topology)


def test_lifecycle_graph_config_file_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    path = root / 'config' / 'system' / 'lifecycle_graph.yaml'
    assert path.exists()
    text = path.read_text(encoding='utf-8')
    assert 'runtime_nodes:' in text
    assert 'inspection_fsm_node' in text
    assert 'inspection_hmi_gateway_server' in text
