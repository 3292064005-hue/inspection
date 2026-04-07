from __future__ import annotations

from pathlib import Path


def test_action_executor_node_hosts_native_action_bridge() -> None:
    path = Path(__file__).resolve().parents[1] / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'action_executor_node.py'
    text = path.read_text(encoding='utf-8')
    assert "native_action_server_enabled" in text
    assert "parameter_as_bool(self, 'native_action_server_enabled', default=True)" in text
    assert 'RosActionBridge(self, enable_servers=parameter_as_bool(' in text
    assert 'submit_native_action_job' in text
    assert 'cancel_native_action_job' in text
    assert 'ActionProvider(' in text


def test_gateway_runtime_disables_native_action_servers_when_executor_enabled() -> None:
    path = Path(__file__).resolve().parents[1] / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'gateway_runtime.py'
    text = path.read_text(encoding='utf-8')
    assert 'INSPECTION_ACTION_EXECUTOR_ENABLED' in text
    assert 'RosActionBridge(self, enable_servers=not self._executor_enabled)' in text



def test_action_executor_node_destroys_bridge_on_shutdown() -> None:
    path = Path(__file__).resolve().parents[1] / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'action_executor_node.py'
    text = path.read_text(encoding='utf-8')
    assert "destroy_bridge = getattr(self.native_action_bridge, 'destroy', None)" in text


def test_ros_action_bridge_exposes_destroy() -> None:
    path = Path(__file__).resolve().parents[1] / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'ros_action_bridge.py'
    text = path.read_text(encoding='utf-8')
    assert 'def destroy(self) -> None:' in text


def test_action_executor_node_deduplicates_before_contract_lookup() -> None:
    path = Path(__file__).resolve().parents[1] / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'action_executor_node.py'
    text = path.read_text(encoding='utf-8')
    dedupe_idx = text.index("existing = self._jobs.get(normalized_job_id)")
    contract_idx = text.index("contract = action_contract(normalized_kind)")
    assert dedupe_idx < contract_idx
