from __future__ import annotations

"""Shared launch builder for the simulated desktop station stack.

This module lives inside the installable ``inspection_bringup`` Python package so
launch entrypoints can import it both from a source workspace and from an
installed ROS environment. Keeping the builder out of the raw ``launch/``
directory avoids fragile relative imports when launch files are executed through
``PythonLaunchDescriptionSource``.
"""

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

try:
    from launch_ros.parameter_descriptions import ParameterValue
except Exception:  # pragma: no cover - launch import smoke stubs
    class ParameterValue:  # type: ignore[override]
        def __init__(self, value, *, value_type=None):
            self.value = value
            self.value_type = value_type



def build_simulated_stack(*, deprecation_notice: str = '') -> LaunchDescription:
    """Build the canonical simulated station stack launch description.

    Args:
        deprecation_notice: Optional message emitted before the simulated stack
            starts. The caller can use this to preserve historical launch entry
            points while steering operators toward the canonical entrypoint.

    Returns:
        LaunchDescription containing the simulated station, action executor, and
        HMI gateway processes.

    Raises:
        No custom exception is raised here. Launch-time dependency resolution is
        delegated to the ROS launch system.

    Boundary behavior:
        All resource defaults resolve from installed package-share directories so
        the launch file behaves the same in source workspaces and installed
        deployments.
    """

    bringup_share = Path(get_package_share_directory('inspection_bringup'))
    gateway_share = Path(get_package_share_directory('inspection_hmi_gateway'))

    profile_name = LaunchConfiguration('profile_name')
    managed_runtime_enabled = LaunchConfiguration('managed_runtime_enabled')
    managed_runtime_autostart = LaunchConfiguration('managed_runtime_autostart')
    native_action_server_enabled = LaunchConfiguration('native_action_server_enabled')
    native_action_client_enabled = LaunchConfiguration('native_action_client_enabled')
    action_executor_enabled = LaunchConfiguration('action_executor_enabled')
    log_root = LaunchConfiguration('log_root')
    recipe_root = LaunchConfiguration('recipe_root')
    frontend_dist = LaunchConfiguration('frontend_dist')
    hmi_port = LaunchConfiguration('hmi_port')
    users_path = LaunchConfiguration('users_path')

    real_station = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(bringup_share / 'launch' / 'real_station.launch.py')),
        launch_arguments={
            'sim_mode': 'true',
            'station_config_path': str(bringup_share / 'config' / 'station' / 'station.yaml'),
            'camera_config_path': str(bringup_share / 'config' / 'camera' / 'camera.yaml'),
            'profile_name': profile_name,
            'managed_runtime_enabled': ParameterValue(managed_runtime_enabled, value_type=bool),
            'managed_runtime_autostart': ParameterValue(managed_runtime_autostart, value_type=bool),
            'log_root': log_root,
            'enable_gateway': 'false',
            'action_executor_enabled': 'false',
        }.items(),
    )
    action_executor = Node(
        package='inspection_hmi_gateway',
        executable='inspection_action_executor_node',
        name='inspection_action_executor_node',
        output='screen',
        condition=IfCondition(action_executor_enabled),
        parameters=[{
            'log_root': log_root,
            'recipe_root': recipe_root,
            'managed_runtime_enabled': ParameterValue(managed_runtime_enabled, value_type=bool),
            'managed_runtime_autostart': ParameterValue(managed_runtime_autostart, value_type=bool),
            'native_action_server_enabled': native_action_server_enabled,
        }],
    )
    gateway = Node(
        package='inspection_hmi_gateway',
        executable='inspection_hmi_gateway_server',
        name='inspection_hmi_gateway_server',
        output='screen',
        additional_env={
            'INSPECTION_HMI_PORT': hmi_port,
            'INSPECTION_HMI_LOG_ROOT': log_root,
            'INSPECTION_HMI_RECIPE_ROOT': recipe_root,
            'INSPECTION_HMI_FRONTEND_DIST': frontend_dist,
            'INSPECTION_HMI_USERS_PATH': users_path,
            'INSPECTION_HMI_REQUIRE_FRONTEND_DIST': '1',
            'INSPECTION_HMI_STRICT_USER_CONFIG': '1',
            'INSPECTION_ACTION_EXECUTOR_ENABLED': action_executor_enabled,
            'INSPECTION_NATIVE_ACTION_CLIENT_ENABLED': native_action_client_enabled,
        },
    )

    actions = [
        DeclareLaunchArgument('profile_name', default_value='simulation'),
        DeclareLaunchArgument('managed_runtime_enabled', default_value='true'),
        DeclareLaunchArgument('managed_runtime_autostart', default_value='true'),
        DeclareLaunchArgument('native_action_server_enabled', default_value='true'),
        DeclareLaunchArgument('native_action_client_enabled', default_value='true'),
        DeclareLaunchArgument('action_executor_enabled', default_value='true'),
        DeclareLaunchArgument('log_root', default_value='logs/runtime'),
        DeclareLaunchArgument('recipe_root', default_value='config/recipes'),
        DeclareLaunchArgument('frontend_dist', default_value=str(gateway_share / 'frontend' / 'dist')),
        DeclareLaunchArgument('hmi_port', default_value='8080'),
        DeclareLaunchArgument('users_path', default_value='config/system/hmi_users.yaml'),
    ]
    if deprecation_notice:
        actions.append(LogInfo(msg=deprecation_notice))
    actions.extend([real_station, action_executor, gateway])
    return LaunchDescription(actions)
