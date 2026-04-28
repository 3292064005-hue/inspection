from __future__ import annotations

import os

import importlib.util
import sys
import types
from pathlib import Path


class _LaunchDescription:
    def __init__(self, actions):
        self.actions = list(actions)


class _DeclareLaunchArgument:
    def __init__(self, name: str, default_value=None):
        self.name = name
        self.default_value = default_value


class _LogInfo:
    def __init__(self, msg=''):
        self.msg = msg


class _OpaqueFunction:
    def __init__(self, *, function):
        self.function = function


class _IncludeLaunchDescription:
    def __init__(self, source, *, launch_arguments=()):
        self.source = source
        self.launch_arguments = tuple(launch_arguments)


class _IfCondition:
    def __init__(self, expression):
        self.expression = expression


class _LaunchConfiguration:
    def __init__(self, name: str):
        self.name = name

    def perform(self, context):
        if isinstance(context, dict):
            return str(context.get(self.name, ''))
        return str(getattr(context, self.name, ''))


class _PythonLaunchDescriptionSource:
    def __init__(self, path: str):
        self.location = path


class _Node:
    def __init__(self, *, package: str, executable: str, name: str, output='screen', parameters=None, additional_env=None, condition=None):
        self.package = package
        self.executable = executable
        self.name = name
        self.output = output
        self.parameters = list(parameters or [])
        self.additional_env = dict(additional_env or {})
        self.condition = condition


class _PackagePaths:
    def __init__(self, root: Path) -> None:
        self.root = root

    def __call__(self, package_name: str) -> str:
        mapping = {
            'inspection_bringup': self.root / 'src' / 'inspection_bringup',
            'inspection_hmi_gateway': self.root / 'src' / 'inspection_hmi_gateway',
        }
        return str(mapping.get(package_name, self.root / package_name))


def _ensure_package_roots() -> Path:
    root = Path(__file__).resolve().parents[2]
    for package_root in [
        root / 'src',
        root / 'src' / 'inspection_bringup',
        root / 'src' / 'inspection_utils',
    ]:
        if str(package_root) not in sys.path:
            sys.path.insert(0, str(package_root))
    return root


def _install_launch_stubs(root: Path) -> None:
    if 'ament_index_python' not in sys.modules:
        sys.modules['ament_index_python'] = types.ModuleType('ament_index_python')
    packages_mod = types.ModuleType('ament_index_python.packages')
    packages_mod.get_package_share_directory = _PackagePaths(root)
    sys.modules['ament_index_python.packages'] = packages_mod

    launch_mod = types.ModuleType('launch')
    launch_mod.LaunchDescription = _LaunchDescription
    sys.modules['launch'] = launch_mod

    actions_mod = types.ModuleType('launch.actions')
    actions_mod.DeclareLaunchArgument = _DeclareLaunchArgument
    actions_mod.LogInfo = _LogInfo
    actions_mod.OpaqueFunction = _OpaqueFunction
    actions_mod.IncludeLaunchDescription = _IncludeLaunchDescription
    sys.modules['launch.actions'] = actions_mod

    conditions_mod = types.ModuleType('launch.conditions')
    conditions_mod.IfCondition = _IfCondition
    sys.modules['launch.conditions'] = conditions_mod

    subs_mod = types.ModuleType('launch.substitutions')
    subs_mod.LaunchConfiguration = _LaunchConfiguration
    sys.modules['launch.substitutions'] = subs_mod

    source_mod = types.ModuleType('launch.launch_description_sources')
    source_mod.PythonLaunchDescriptionSource = _PythonLaunchDescriptionSource
    sys.modules['launch.launch_description_sources'] = source_mod

    launch_ros_mod = types.ModuleType('launch_ros')
    sys.modules['launch_ros'] = launch_ros_mod
    launch_ros_actions = types.ModuleType('launch_ros.actions')
    launch_ros_actions.Node = _Node
    sys.modules['launch_ros.actions'] = launch_ros_actions


def _load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _declared_defaults(description: _LaunchDescription) -> dict[str, str]:
    defaults: dict[str, str] = {}
    for action in description.actions:
        if isinstance(action, _DeclareLaunchArgument):
            defaults[action.name] = str(action.default_value)
    return defaults


def test_sim_stack_launch_module_imports_without_relative_import_failures() -> None:
    root = _ensure_package_roots()
    _install_launch_stubs(root)
    sim_module = _load_module(root / 'src' / 'inspection_bringup' / 'launch' / 'sim_stack.launch.py', 'inspection_tests.sim_stack_launch_smoke')

    sim_description = sim_module.generate_launch_description()

    assert isinstance(sim_description, _LaunchDescription)
    assert sim_description.actions
    assert not (root / 'src' / 'inspection_bringup' / 'launch' / 'full_stack.launch.py').exists()


def test_offline_replay_launch_uses_absolute_resource_defaults_and_managed_runtime_arguments() -> None:
    root = _ensure_package_roots()
    _install_launch_stubs(root)
    module = _load_module(root / 'src' / 'inspection_bringup' / 'launch' / 'offline_replay.launch.py', 'inspection_tests.offline_replay_launch_smoke')
    description = module.generate_launch_description()
    defaults = _declared_defaults(description)

    assert defaults['recipe_path'].endswith('/config/recipes/default_recipe.yaml')
    assert defaults['station_config_path'].endswith('/config/station/station.yaml')
    assert defaults['camera_config_path'].endswith('/config/camera/camera.yaml')
    assert defaults['compatibility_path'].endswith('/config/compatibility/matrix.yaml')
    assert defaults['managed_runtime_enabled'] == 'true'
    assert defaults['managed_runtime_autostart'] == 'true'
    assert any(isinstance(action, _OpaqueFunction) for action in description.actions)


def test_real_station_launch_exposes_absolute_profile_snapshot_payload() -> None:
    root = _ensure_package_roots()
    _install_launch_stubs(root)
    runtime_launch_config = _load_module(
        root / 'src' / 'inspection_bringup' / 'inspection_bringup' / 'runtime_launch_config.py',
        'inspection_tests.runtime_launch_config_smoke',
    )

    payload = runtime_launch_config.build_launch_runtime_payload(
        recipe_path='config/recipes/default_recipe.yaml',
        station_config_path='config/station/station_stm32.yaml',
        camera_config_path='config/camera/camera_esp32s3.yaml',
        profile_name='production',
        compatibility_path='config/compatibility/matrix.yaml',
    )

    profile_path = payload['resolved_paths']['profile_path']
    assert Path(runtime_launch_config.__file__).is_absolute()
    assert Path(profile_path).is_absolute()
    assert profile_path.endswith('/config/profiles/production.yaml')


def test_runtime_launch_payload_preserves_esp32_camera_parameters() -> None:
    from inspection_bringup import runtime_launch_config

    payload = runtime_launch_config.build_launch_runtime_payload(
        recipe_path='config/recipes/default_recipe.yaml',
        station_config_path='config/station/station_stm32.yaml',
        camera_config_path='config/camera/camera_esp32s3.yaml',
        profile_name='production',
        compatibility_path='config/compatibility/matrix.yaml',
    )
    camera_params = payload['camera_parameters']
    assert camera_params['camera_provider'] == 'esp32_http'
    assert camera_params['esp32_base_url'].startswith('http://')
    assert payload['effective_bundle']['station']['adapter_name'] == 'serial'


def test_real_station_launch_uses_real_hardware_defaults() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_bringup' / 'launch' / 'real_station.launch.py').read_text(encoding='utf-8')
    assert "DeclareLaunchArgument('sim_mode', default_value='false')" in text
    assert 'station_stm32.yaml' in text
    assert 'camera_esp32s3.yaml' in text



def test_simulation_launch_payload_uses_mock_station_capability_profile() -> None:
    from inspection_bringup import runtime_launch_config

    payload = runtime_launch_config.build_launch_runtime_payload(
        recipe_path='config/recipes/default_recipe.yaml',
        station_config_path='config/station/station.yaml',
        camera_config_path='config/camera/camera.yaml',
        profile_name='simulation',
        compatibility_path='config/compatibility/matrix.yaml',
    )
    station_params = payload['station_parameters']
    assert station_params['adapter_name'] == 'mock'
    assert station_params['station_capability_profile'] == 'simulation_station_default'
