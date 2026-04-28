from pathlib import Path

from inspection_hmi_gateway.action_contract import ACTION_CONTRACTS


def test_public_generated_allowed_actions_have_matching_ros_action_definitions() -> None:
    root = Path(__file__).resolve().parents[2]
    action_dir = root / 'src' / 'inspection_interfaces' / 'action'
    expected = {
        contract.ros_type
        for contract in ACTION_CONTRACTS.values()
        if contract.capability.execution_policy == 'allowed' and contract.capability.generated_client and contract.capability.public_catalog
    }
    actual = {path.stem for path in action_dir.glob('*.action')}
    assert expected <= actual


def test_native_transport_registry_surface_covers_newly_promoted_actions() -> None:
    catalog = {kind: contract.ros_type for kind, contract in ACTION_CONTRACTS.items()}
    assert catalog['stop_station'] == 'StopStation'
    assert catalog['set_maintenance_mode'] == 'SetMaintenanceMode'
    assert catalog['create_batch'] == 'CreateBatch'
    assert catalog['diagnostic_capture_frame'] == 'DiagnosticCaptureFrame'
    assert catalog['diagnostic_test_lighting'] == 'DiagnosticTestLighting'
    assert catalog['diagnostic_test_sort_actuator'] == 'DiagnosticTestSortActuator'



def test_public_generated_allowed_actions_have_result_json_terminal_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    action_dir = root / "src" / "inspection_interfaces" / "action"
    expected = {
        contract.ros_type
        for contract in ACTION_CONTRACTS.values()
        if contract.capability.execution_policy == "allowed" and contract.capability.generated_client and contract.capability.public_catalog
    }
    for ros_type in expected:
        text = (action_dir / f"{ros_type}.action").read_text(encoding="utf-8")
        assert "string result_json" in text
