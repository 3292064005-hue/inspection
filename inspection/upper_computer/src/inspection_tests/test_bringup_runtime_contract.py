from pathlib import Path


def test_bringup_launch_exposes_managed_runtime_args() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_bringup' / 'launch' / 'real_station.launch.py').read_text(encoding='utf-8')
    assert 'managed_runtime_enabled' in text
    assert 'managed_runtime_autostart' in text


def test_full_stack_launch_forwards_managed_runtime_args() -> None:
    root = Path(__file__).resolve().parents[2]
    wrapper = (root / 'src' / 'inspection_bringup' / 'launch' / 'full_stack.launch.py').read_text(encoding='utf-8')
    helper = (root / 'src' / 'inspection_bringup' / 'inspection_bringup' / 'sim_stack_common.py').read_text(encoding='utf-8')
    assert 'build_simulated_stack' in wrapper
    assert 'managed_runtime_enabled' in helper
    assert 'managed_runtime_autostart' in helper



def test_full_stack_launch_starts_action_executor_node() -> None:
    root = Path(__file__).resolve().parents[2]
    wrapper = (root / 'src' / 'inspection_bringup' / 'launch' / 'full_stack.launch.py').read_text(encoding='utf-8')
    helper = (root / 'src' / 'inspection_bringup' / 'inspection_bringup' / 'sim_stack_common.py').read_text(encoding='utf-8')
    assert 'build_simulated_stack' in wrapper
    assert 'INSPECTION_ACTION_EXECUTOR_ENABLED' in helper
    assert 'action_executor_enabled' in helper
    assert 'IfCondition(action_executor_enabled)' in helper
    assert 'native_action_server_enabled' in helper
    assert 'managed_runtime_enabled' in helper
    assert 'managed_runtime_autostart' in helper


def test_gateway_launch_starts_action_executor_node() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_hmi_gateway' / 'launch' / 'hmi_gateway.launch.py').read_text(encoding='utf-8')
    assert 'inspection_action_executor_node' in text
    assert 'INSPECTION_ACTION_EXECUTOR_ENABLED' in text
    assert 'action_executor_enabled' in text
    assert 'IfCondition(action_executor_enabled)' in text
    assert 'native_action_server_enabled' in text
    assert 'managed_runtime_enabled' in text
    assert 'managed_runtime_autostart' in text


def test_humble_runtime_validation_script_exists() -> None:
    root = Path(__file__).resolve().parents[2]
    script = root / 'scripts' / 'run_ros2_humble_runtime_validation.sh'
    assert script.exists()
    text = script.read_text(encoding='utf-8')
    assert '/opt/ros/humble/setup.bash' in text
    assert 'install/setup.bash' in text
    assert 'run_launch_test_matrix.sh' in text
    assert '--packages-select inspection_tests' not in text


def test_launch_runtime_validation_uses_absolute_paths() -> None:
    root = Path(__file__).resolve().parents[2]
    full_stack = (root / 'src' / 'inspection_tests' / 'launch' / 'full_stack_runtime_validation.launch.py').read_text(encoding='utf-8')
    native_qos = (root / 'src' / 'inspection_tests' / 'launch' / 'native_lifecycle_qos_validation.launch.py').read_text(encoding='utf-8')
    assert "ROOT_DIR = Path(__file__).resolve().parents[3]" in full_stack
    assert "DEFAULT_RECIPE_PATH = str(ROOT_DIR / 'config' / 'recipes' / 'default_recipe.yaml')" in full_stack
    assert "log_root': RUNTIME_LOG_ROOT" in full_stack
    assert "recipe_path': DEFAULT_RECIPE_PATH" in full_stack
    assert "ROOT_DIR = Path(__file__).resolve().parents[3]" in native_qos
    assert "DEFAULT_RECIPE_PATH = str(ROOT_DIR / 'config' / 'recipes' / 'default_recipe.yaml')" in native_qos
    assert "log_root': RUNTIME_LOG_ROOT" in native_qos
    assert "recipe_path': DEFAULT_RECIPE_PATH" in native_qos


def test_real_station_launch_uses_canonical_control_plane_node_names() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_bringup' / 'launch' / 'real_station.launch.py').read_text(encoding='utf-8')
    assert "name='inspection_fsm_node'" in text
    assert "name='inspection_orchestrator_node'" in text


def test_launches_use_absolute_resource_defaults_and_runtime_log_root() -> None:
    root = Path(__file__).resolve().parents[2]
    full_stack = (root / 'src' / 'inspection_bringup' / 'launch' / 'full_stack.launch.py').read_text(encoding='utf-8')
    gateway = (root / 'src' / 'inspection_hmi_gateway' / 'launch' / 'hmi_gateway.launch.py').read_text(encoding='utf-8')
    assert 'log_root' in full_stack
    assert 'get_package_share_directory' in gateway
    assert 'log_root' in gateway


def test_launch_runtime_validation_uses_discovered_launch_matrix() -> None:
    root = Path(__file__).resolve().parents[2]
    script = (root / 'scripts' / 'run_launch_test_matrix.sh').read_text(encoding='utf-8')
    assert "find \"$LAUNCH_DIR\" -maxdepth 1 -type f -name '*.launch.py'" in script
    assert 'python -m pytest' in script


def test_sim_stack_launch_exists_as_canonical_demo_entrypoint() -> None:
    root = Path(__file__).resolve().parents[2]
    sim_stack = root / 'src' / 'inspection_bringup' / 'launch' / 'sim_stack.launch.py'
    assert sim_stack.exists()
    wrapper = sim_stack.read_text(encoding='utf-8')
    helper = (root / 'src' / 'inspection_bringup' / 'inspection_bringup' / 'sim_stack_common.py').read_text(encoding='utf-8')
    assert 'build_simulated_stack' in wrapper
    assert "sim_mode': 'true'" in helper
    assert 'INSPECTION_HMI_REQUIRE_FRONTEND_DIST' in helper
    assert "DeclareLaunchArgument('profile_name', default_value='simulation')" in helper

def test_real_station_launch_materializes_effective_runtime_payload() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_bringup' / 'launch' / 'real_station.launch.py').read_text(encoding='utf-8')
    assert 'OpaqueFunction' in text
    assert 'build_launch_runtime_payload' in text
    assert "'profile_config_path': resolved['profile_path']" in text
    assert text.count("'profile_config_path': resolved['profile_path']") >= 3


def test_runtime_launch_payload_forwards_esp32_auth_settings() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_bringup' / 'inspection_bringup' / 'runtime_launch_config.py').read_text(encoding='utf-8')
    assert "'esp32_auth_header'" in text
    assert "'esp32_auth_token'" in text


def test_real_station_launch_defaults_to_real_hardware_configs() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_bringup' / 'launch' / 'real_station.launch.py').read_text(encoding='utf-8')
    assert "DeclareLaunchArgument('sim_mode', default_value='false')" in text
    assert 'station_stm32.yaml' in text
    assert 'camera_esp32s3.yaml' in text
    assert '_REAL_ENTRY_SIM_WARNING' in text
    assert 'resolved simulated config(s) in real mode' in text


def test_real_station_launch_starts_fullstack_gateway_and_executor_by_default() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_bringup' / 'launch' / 'real_station.launch.py').read_text(encoding='utf-8')
    assert "DeclareLaunchArgument('enable_gateway', default_value='true')" in text
    assert "DeclareLaunchArgument('action_executor_enabled', default_value='true')" in text
    assert 'inspection_hmi_gateway_server' in text
    assert 'inspection_action_executor_node' in text
    assert 'INSPECTION_ACTION_EXECUTOR_ENABLED' in text
    assert 'station_protocol_version' in text
