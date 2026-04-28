from pathlib import Path

from inspection_utils.transport_boundary import transport_bridge_matrix, transport_bridge_policy

ROOT = Path(__file__).resolve().parents[2]


def test_transport_bridge_policy_catalog_contains_required_channels() -> None:
    matrix = transport_bridge_matrix()
    names = {item['name'] for item in matrix}
    assert {'control', 'capture_request', 'diagnostics', 'supervisor_command', 'supervisor_state', 'action_executor_event'}.issubset(names)

    control = transport_bridge_policy('control').to_dict()
    assert control['boundary'] == 'edge_bridge'
    assert control['coreTransport'] == 'typed'
    assert control['legacyPublishEnabled'] is False


def test_transport_bridge_policy_allows_env_based_legacy_rollback(monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_TRANSPORT_LEGACY_CONTROL_ENABLED', '1')
    control = transport_bridge_policy('control').to_dict()
    assert control['legacyPublishEnabled'] is True


def test_fsm_legacy_sort_mirror_is_disabled_by_default() -> None:
    text = (ROOT / 'src' / 'inspection_fsm' / 'inspection_fsm' / 'fsm_node.py').read_text(encoding='utf-8')
    assert "self.declare_parameter('publish_legacy_sort_cmd', False)" in text
    assert "parameter_as_bool(self, 'publish_legacy_sort_cmd', default=False)" in text
