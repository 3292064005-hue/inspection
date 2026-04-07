from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_split_release_manifest_is_generated_from_version_source_of_truth() -> None:
    manifest = (_repo_root() / 'release' / 'split_release_manifest.yaml').read_text(encoding='utf-8')
    assert "protocolVersion: '1.0'" in manifest
    assert 'stm32-station-pio-v1' in manifest
    assert 'esp32s3-camera-pio-v1' in manifest
    assert "generatedFrom: release/version_manifest.yaml" in manifest
    assert (_repo_root() / 'release' / 'version_manifest.yaml').exists()


def test_split_delivery_ci_covers_upper_computer_firmware_and_protocol_gate() -> None:
    workflow = _repo_root() / '.github' / 'workflows' / 'split_delivery_ci.yml'
    assert workflow.exists()
    text = workflow.read_text(encoding='utf-8')
    assert 'upper_computer_workspace_gate' in text
    assert 'upper_computer_ros_release_gate' in text
    assert 'firmware_platformio_build' in text
    assert 'firmware_contract_gate' in text
    assert 'split_protocol_contract_gate' in text
    assert 'platformio run' in text
    assert 'run_ros2_humble_runtime_validation.sh' in text
    assert 'validate_release_versions.py' in text
    assert 'run_firmware_contract_tests.sh' in text


def test_split_delivery_packaging_scripts_exist_and_filter_generated_assets() -> None:
    source_script = _repo_root() / 'scripts' / 'build_source_package.sh'
    release_script = _repo_root() / 'scripts' / 'build_release_bundle.sh'
    assert source_script.exists()
    assert release_script.exists()
    source_text = source_script.read_text(encoding='utf-8')
    release_text = release_script.read_text(encoding='utf-8')
    assert 'frontend/node_modules' in source_text
    assert 'frontend/dist' in source_text
    assert '.artifacts' in source_text
    assert '.pio' in source_text
    assert 'release/split_release_manifest.yaml' not in source_text
    assert 'release' in release_text
    assert '.github' in release_text
    assert 'frontend/node_modules' in release_text
    assert '.artifacts' in release_text


def test_runtime_nodes_import_new_runtime_helpers() -> None:
    root = _repo_root() / 'upper_computer' / 'src'
    action_executor = (root / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'action_executor_node.py').read_text(encoding='utf-8')
    logger_node = (root / 'inspection_logger' / 'inspection_logger' / 'logger_node.py').read_text(encoding='utf-8')
    processor_node = (root / 'vision_processing' / 'vision_processing' / 'processor_node.py').read_text(encoding='utf-8')
    assert 'from inspection_utils.param_parsing import parameter_as_bool' in action_executor
    assert 'from inspection_utils.transport_adapters import legacy_payload_json_from_typed_message' in logger_node
    assert 'from inspection_utils.typed_interfaces import assert_typed_interfaces_available' in logger_node
    assert 'from inspection_utils.transport_adapters import legacy_payload_json_from_typed_message' in processor_node
    assert 'from inspection_utils.typed_interfaces import assert_typed_interfaces_available' in processor_node
