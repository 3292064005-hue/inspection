from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

try:
    from launch_ros.parameter_descriptions import ParameterValue
except Exception:  # pragma: no cover - launch import smoke stubs
    class ParameterValue:  # type: ignore[override]
        def __init__(self, value, *, value_type=None):
            self.value = value
            self.value_type = value_type



def generate_launch_description():
    package_share = Path(get_package_share_directory('inspection_hmi_gateway'))
    managed_runtime_enabled = LaunchConfiguration('managed_runtime_enabled')
    managed_runtime_autostart = LaunchConfiguration('managed_runtime_autostart')
    native_action_server_enabled = LaunchConfiguration('native_action_server_enabled')
    native_action_client_enabled = LaunchConfiguration('native_action_client_enabled')
    action_executor_enabled = LaunchConfiguration('action_executor_enabled')
    log_root = LaunchConfiguration('log_root')
    recipe_root = LaunchConfiguration('recipe_root')
    frontend_dist = LaunchConfiguration('frontend_dist')
    users_path = LaunchConfiguration('users_path')
    hmi_port = LaunchConfiguration('hmi_port')
    require_frontend_dist = LaunchConfiguration('require_frontend_dist')
    return LaunchDescription([
        DeclareLaunchArgument('managed_runtime_enabled', default_value='true'),
        DeclareLaunchArgument('managed_runtime_autostart', default_value='true'),
        DeclareLaunchArgument('native_action_server_enabled', default_value='true'),
        DeclareLaunchArgument('native_action_client_enabled', default_value='true'),
        DeclareLaunchArgument('action_executor_enabled', default_value='true'),
        DeclareLaunchArgument('log_root', default_value='logs/runtime'),
        DeclareLaunchArgument('recipe_root', default_value='config/recipes'),
        DeclareLaunchArgument('frontend_dist', default_value=str(package_share / 'frontend' / 'dist')),
        DeclareLaunchArgument('hmi_port', default_value='8080'),
        DeclareLaunchArgument('require_frontend_dist', default_value='false'),
        DeclareLaunchArgument('users_path', default_value='config/system/hmi_users.yaml'),
        Node(
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
                'native_action_server_enabled': ParameterValue(native_action_server_enabled, value_type=bool),
            }],
        ),
        Node(
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
                'INSPECTION_HMI_REQUIRE_FRONTEND_DIST': require_frontend_dist,
                'INSPECTION_ACTION_EXECUTOR_ENABLED': action_executor_enabled,
                'INSPECTION_NATIVE_ACTION_CLIENT_ENABLED': native_action_client_enabled,
            },
        ),
    ])
