from __future__ import annotations

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from inspection_bringup.runtime_launch_config import build_launch_runtime_payload
from inspection_utils.param_parsing import coerce_bool



def _launch_setup(context, *_args, **_kwargs):
    profile_name = LaunchConfiguration('profile_name').perform(context)
    recipe_path = LaunchConfiguration('recipe_path').perform(context)
    station_config_path = LaunchConfiguration('station_config_path').perform(context)
    camera_config_path = LaunchConfiguration('camera_config_path').perform(context)
    compatibility_path = LaunchConfiguration('compatibility_path').perform(context)
    log_root = LaunchConfiguration('log_root').perform(context)
    managed_runtime_enabled = LaunchConfiguration('managed_runtime_enabled').perform(context)
    managed_runtime_autostart = LaunchConfiguration('managed_runtime_autostart').perform(context)
    managed_runtime_params = {
        'managed_runtime_enabled': coerce_bool(managed_runtime_enabled, default=True),
        'managed_runtime_autostart': coerce_bool(managed_runtime_autostart, default=True),
    }

    payload = build_launch_runtime_payload(
        recipe_path=recipe_path,
        station_config_path=station_config_path,
        camera_config_path=camera_config_path,
        profile_name=profile_name,
        compatibility_path=compatibility_path,
    )
    resolved = payload['resolved_paths']
    camera_parameters = dict(payload['camera_parameters'])
    camera_parameters.update({'mock_mode': True, 'mock_color': 'green'})

    return [
        Node(package='vision_acquisition', executable='camera_node', name='camera_node', parameters=[camera_parameters, managed_runtime_params]),
        Node(package='vision_processing', executable='vision_processor_node', name='vision_processor_node', parameters=[{'recipe_path': resolved['recipe_path'], 'output_dir': log_root, 'camera_config_path': resolved['camera_config_path'], 'profile_name': profile_name, 'profile_config_path': resolved['profile_path'], 'compatibility_path': resolved['compatibility_path']}, managed_runtime_params]),
        Node(package='inspection_logger', executable='logger_node', name='inspection_logger_node', parameters=[{'log_root': log_root, 'recipe_path': resolved['recipe_path'], 'station_config_path': resolved['station_config_path'], 'camera_config_path': resolved['camera_config_path'], 'profile_name': profile_name, 'profile_config_path': resolved['profile_path']}, managed_runtime_params]),
        Node(package='inspection_diagnostics', executable='diagnostics_node', name='inspection_diagnostics_node', parameters=[managed_runtime_params]),
        Node(package='inspection_supervisor', executable='supervisor_node', name='inspection_supervisor_node', parameters=[{'profile_name': profile_name, 'autostart_mode': 'BENCHMARK'}, managed_runtime_params]),
        Node(package='inspection_orchestrator', executable='orchestrator_node', name='inspection_orchestrator_node', parameters=[{'auto_recover': False}, managed_runtime_params]),
    ]


def generate_launch_description() -> LaunchDescription:
    bringup_share = Path(get_package_share_directory('inspection_bringup'))
    default_recipe_path = str(bringup_share / 'config' / 'recipes' / 'default_recipe.yaml')
    default_station_config = str(bringup_share / 'config' / 'station' / 'station.yaml')
    default_camera_config = str(bringup_share / 'config' / 'camera' / 'camera.yaml')
    default_compatibility_path = str(bringup_share / 'config' / 'compatibility' / 'matrix.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('recipe_path', default_value=default_recipe_path),
        DeclareLaunchArgument('station_config_path', default_value=default_station_config),
        DeclareLaunchArgument('camera_config_path', default_value=default_camera_config),
        DeclareLaunchArgument('profile_name', default_value='benchmark'),
        DeclareLaunchArgument('compatibility_path', default_value=default_compatibility_path),
        DeclareLaunchArgument('log_root', default_value='logs/runtime'),
        DeclareLaunchArgument('managed_runtime_enabled', default_value='true'),
        DeclareLaunchArgument('managed_runtime_autostart', default_value='true'),
        OpaqueFunction(function=_launch_setup),
    ])
