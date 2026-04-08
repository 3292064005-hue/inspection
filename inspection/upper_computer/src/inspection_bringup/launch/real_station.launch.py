from __future__ import annotations

from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from inspection_bringup.runtime_launch_config import build_launch_runtime_payload
from inspection_utils.param_parsing import coerce_bool

_REAL_ENTRY_SIM_WARNING = '[inspection_bringup] real_station.launch.py is running in simulation mode by explicit override.'


def _launch_setup(context, *_args, **_kwargs):
    """Build the effective real-station launch graph.

    Args:
        context: ROS launch context used to resolve substitutions.

    Returns:
        Launch actions for the production station graph.

    Raises:
        RuntimeError: When real mode resolves simulation-only configs.

    Boundary behavior:
        The launch file materializes the same effective runtime bundle used by
        config validation before any node is started. Gateway and executor
        processes can be disabled explicitly for split deployments.
    """
    profile_name = LaunchConfiguration('profile_name').perform(context)
    sim_mode = coerce_bool(LaunchConfiguration('sim_mode').perform(context), default=False)
    recipe_path = LaunchConfiguration('recipe_path').perform(context)
    station_config_path = LaunchConfiguration('station_config_path').perform(context)
    camera_config_path = LaunchConfiguration('camera_config_path').perform(context)
    compatibility_path = LaunchConfiguration('compatibility_path').perform(context)
    orchestrator_config_path = LaunchConfiguration('orchestrator_config_path').perform(context)
    log_root = LaunchConfiguration('log_root').perform(context)
    recipe_root = LaunchConfiguration('recipe_root').perform(context)
    frontend_dist = LaunchConfiguration('frontend_dist').perform(context)
    hmi_port = LaunchConfiguration('hmi_port').perform(context)
    users_path = LaunchConfiguration('users_path').perform(context)
    enable_bag_recording = coerce_bool(LaunchConfiguration('enable_bag_recording').perform(context), default=False)
    enable_annotated_image_diagnostics = coerce_bool(LaunchConfiguration('enable_annotated_image_diagnostics').perform(context), default=False)
    supervisor_health_timeout_sec = LaunchConfiguration('supervisor_health_timeout_sec').perform(context)
    managed_runtime_enabled = coerce_bool(LaunchConfiguration('managed_runtime_enabled').perform(context), default=True)
    managed_runtime_autostart = coerce_bool(LaunchConfiguration('managed_runtime_autostart').perform(context), default=True)
    enable_gateway = coerce_bool(LaunchConfiguration('enable_gateway').perform(context), default=True)
    action_executor_enabled = coerce_bool(LaunchConfiguration('action_executor_enabled').perform(context), default=True)
    native_action_server_enabled = coerce_bool(LaunchConfiguration('native_action_server_enabled').perform(context), default=True)
    native_action_client_enabled = coerce_bool(LaunchConfiguration('native_action_client_enabled').perform(context), default=True)
    require_frontend_dist = coerce_bool(LaunchConfiguration('require_frontend_dist').perform(context), default=True)
    strict_user_config = coerce_bool(LaunchConfiguration('strict_user_config').perform(context), default=True)
    managed_runtime_params = {
        'managed_runtime_enabled': managed_runtime_enabled,
        'managed_runtime_autostart': managed_runtime_autostart,
    }
    payload = build_launch_runtime_payload(
        recipe_path=recipe_path,
        station_config_path=station_config_path,
        camera_config_path=camera_config_path,
        profile_name=profile_name,
        compatibility_path=compatibility_path,
    )
    resolved = payload['resolved_paths']
    if not sim_mode:
        invalid = []
        if Path(resolved['station_config_path']).name == 'station.yaml':
            invalid.append('station.yaml')
        if Path(resolved['camera_config_path']).name == 'camera.yaml':
            invalid.append('camera.yaml')
        if invalid:
            raise RuntimeError(f"resolved simulated config(s) in real mode: {', '.join(invalid)}")
    effective_bundle = payload['effective_bundle']
    camera_parameters = dict(payload['camera_parameters'])
    camera_parameters['mock_mode'] = sim_mode
    camera_parameters.setdefault('mock_color', 'red')
    station_parameters = dict(payload['station_parameters'])
    station_parameters['sim_mode'] = sim_mode
    fsm_parameters = dict(payload['fsm_parameters'])
    fsm_parameters.update({'auto_start': True, 'profile_name': profile_name})
    summary = effective_bundle['summary']
    actions = []
    if sim_mode:
        actions.append(LogInfo(msg=_REAL_ENTRY_SIM_WARNING))
    actions.extend([
        LogInfo(
            msg=(
                '[inspection_bringup] real_station profile='
                f"{summary['profile_name']} sim_mode={str(sim_mode).lower()} "
                f"station_adapter={summary['station_adapter']} protocol={summary['station_protocol_version']} "
                f"gateway={str(enable_gateway).lower()} action_executor={str(action_executor_enabled).lower()} "
                f"camera_hz={summary['camera_hz']} decision_overrides={','.join(summary['decision_overrides']) or 'none'}"
            )
        ),
        Node(package='vision_acquisition', executable='camera_node', name='camera_node', parameters=[camera_parameters, managed_runtime_params]),
        Node(
            package='vision_processing',
            executable='vision_processor_node',
            name='vision_processor_node',
            parameters=[
                {
                    'recipe_path': resolved['recipe_path'],
                    'output_dir': log_root,
                    'camera_config_path': resolved['camera_config_path'],
                    'profile_name': profile_name,
                    'profile_config_path': resolved['profile_path'],
                    'compatibility_path': resolved['compatibility_path'],
                },
                managed_runtime_params,
            ],
        ),
        Node(
            package='inspection_decision',
            executable='decision_node',
            name='decision_node',
            parameters=[
                {
                    'recipe_path': resolved['recipe_path'],
                    'profile_name': profile_name,
                    'profile_config_path': resolved['profile_path'],
                    'camera_config_path': resolved['camera_config_path'],
                    'station_config_path': resolved['station_config_path'],
                    'compatibility_path': resolved['compatibility_path'],
                },
                managed_runtime_params,
            ],
        ),
        Node(package='station_bridge', executable='station_bridge_node', name='station_bridge_node', parameters=[station_parameters, managed_runtime_params]),
        Node(package='inspection_fsm', executable='fsm_node', name='inspection_fsm_node', parameters=[fsm_parameters, managed_runtime_params]),
        Node(
            package='inspection_logger',
            executable='logger_node',
            name='inspection_logger_node',
            parameters=[
                {
                    'log_root': log_root,
                    'recipe_path': resolved['recipe_path'],
                    'station_config_path': resolved['station_config_path'],
                    'camera_config_path': resolved['camera_config_path'],
                    'profile_name': profile_name,
                    'profile_config_path': resolved['profile_path'],
                    'enable_bag_recording': enable_bag_recording,
                },
                managed_runtime_params,
            ],
        ),
        Node(package='inspection_diagnostics', executable='diagnostics_node', name='inspection_diagnostics_node', parameters=[{'enable_annotated_image_diagnostics': enable_annotated_image_diagnostics}, managed_runtime_params]),
        Node(package='inspection_supervisor', executable='supervisor_node', name='inspection_supervisor_node', parameters=[{'profile_name': profile_name, 'health_timeout_sec': supervisor_health_timeout_sec}, managed_runtime_params]),
        Node(package='inspection_orchestrator', executable='orchestrator_node', name='inspection_orchestrator_node', parameters=[orchestrator_config_path, managed_runtime_params]),
        Node(package='inspection_hmi', executable='hmi_node', name='inspection_hmi_node'),
    ])
    if action_executor_enabled:
        actions.append(
            Node(
                package='inspection_hmi_gateway',
                executable='inspection_action_executor_node',
                name='inspection_action_executor_node',
                output='screen',
                parameters=[
                    {
                        'log_root': log_root,
                        'recipe_root': recipe_root,
                        'managed_runtime_enabled': managed_runtime_enabled,
                        'managed_runtime_autostart': managed_runtime_autostart,
                        'native_action_server_enabled': native_action_server_enabled,
                    }
                ],
            )
        )
    if enable_gateway:
        actions.append(
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
                    'INSPECTION_HMI_REQUIRE_FRONTEND_DIST': '1' if require_frontend_dist else '0',
                    'INSPECTION_HMI_STRICT_USER_CONFIG': '1' if strict_user_config else '0',
                    'INSPECTION_ACTION_EXECUTOR_ENABLED': 'true' if action_executor_enabled else 'false',
                    'INSPECTION_NATIVE_ACTION_CLIENT_ENABLED': 'true' if native_action_client_enabled else 'false',
                },
            )
        )
    return actions


def generate_launch_description() -> LaunchDescription:
    bringup_share = Path(get_package_share_directory('inspection_bringup'))
    gateway_share = Path(get_package_share_directory('inspection_hmi_gateway'))
    default_recipe_path = str(bringup_share / 'config' / 'recipes' / 'default_recipe.yaml')
    default_station_config = str(bringup_share / 'config' / 'station' / 'station_stm32.yaml')
    default_camera_config = str(bringup_share / 'config' / 'camera' / 'camera_esp32s3.yaml')
    default_compatibility_path = str(bringup_share / 'config' / 'compatibility' / 'matrix.yaml')
    return LaunchDescription([
        DeclareLaunchArgument('sim_mode', default_value='false'),
        DeclareLaunchArgument('recipe_path', default_value=default_recipe_path),
        DeclareLaunchArgument('station_config_path', default_value=default_station_config),
        DeclareLaunchArgument('camera_config_path', default_value=default_camera_config),
        DeclareLaunchArgument('log_root', default_value='logs/runtime'),
        DeclareLaunchArgument('recipe_root', default_value='config/recipes'),
        DeclareLaunchArgument('frontend_dist', default_value=str(gateway_share / 'frontend' / 'dist')),
        DeclareLaunchArgument('users_path', default_value='config/system/hmi_users.yaml'),
        DeclareLaunchArgument('hmi_port', default_value='8080'),
        DeclareLaunchArgument('profile_name', default_value='production'),
        DeclareLaunchArgument('compatibility_path', default_value=default_compatibility_path),
        DeclareLaunchArgument('orchestrator_config_path', default_value=str(bringup_share / 'config' / 'system' / 'orchestrator.yaml')),
        DeclareLaunchArgument('enable_bag_recording', default_value='false'),
        DeclareLaunchArgument('enable_annotated_image_diagnostics', default_value='false'),
        DeclareLaunchArgument('supervisor_health_timeout_sec', default_value='3.0'),
        DeclareLaunchArgument('managed_runtime_enabled', default_value='true'),
        DeclareLaunchArgument('managed_runtime_autostart', default_value='true'),
        DeclareLaunchArgument('enable_gateway', default_value='true'),
        DeclareLaunchArgument('action_executor_enabled', default_value='true'),
        DeclareLaunchArgument('native_action_server_enabled', default_value='true'),
        DeclareLaunchArgument('native_action_client_enabled', default_value='true'),
        DeclareLaunchArgument('require_frontend_dist', default_value='true'),
        DeclareLaunchArgument('strict_user_config', default_value='true'),
        OpaqueFunction(function=_launch_setup),
    ])
