import tempfile
import time
from pathlib import Path

import pytest

launch_testing = pytest.importorskip('launch_testing')
launch = pytest.importorskip('launch')
launch_ros = pytest.importorskip('launch_ros')
rclpy = pytest.importorskip('rclpy')
from std_msgs.msg import String

from inspection_supervisor.native_lifecycle_probe import NativeLifecycleProbe
from inspection_utils.logging_tools import safe_json_loads

ROOT_DIR = Path(__file__).resolve().parents[3]
RUNTIME_LOG_ROOT = str(Path(tempfile.gettempdir()) / 'inspection_runtime_validation_logs')
DEFAULT_RECIPE_PATH = str(ROOT_DIR / 'config' / 'recipes' / 'default_recipe.yaml')

EXPECTED_NODES = [
    'inspection_action_executor_node',
    'inspection_logger_node',
    'inspection_diagnostics_node',
    'decision_node',
]


def generate_test_description():
    actions = [
        launch_ros.actions.Node(
            package='inspection_hmi_gateway', executable='inspection_action_executor_node', name='inspection_action_executor_node', output='screen',
            parameters=[{'managed_runtime_enabled': True, 'managed_runtime_autostart': True, 'native_action_server_enabled': True, 'log_root': RUNTIME_LOG_ROOT}],
        ),
        launch_ros.actions.Node(
            package='inspection_logger', executable='logger_node', name='inspection_logger_node', output='screen',
            parameters=[{'managed_runtime_enabled': True, 'managed_runtime_autostart': True, 'log_root': RUNTIME_LOG_ROOT}],
        ),
        launch_ros.actions.Node(
            package='inspection_diagnostics', executable='diagnostics_node', name='inspection_diagnostics_node', output='screen',
            parameters=[{'managed_runtime_enabled': True, 'managed_runtime_autostart': True}],
        ),
        launch_ros.actions.Node(
            package='inspection_decision', executable='decision_node', name='decision_node', output='screen',
            parameters=[{'managed_runtime_enabled': True, 'managed_runtime_autostart': True, 'recipe_path': DEFAULT_RECIPE_PATH}],
        ),
    ]
    return launch.LaunchDescription(actions + [launch_testing.actions.ReadyToTest()]), {'actions': actions}


class _Collector:
    def __init__(self):
        self.events = []

    def on_event(self, msg: String):
        payload = safe_json_loads(msg.data)
        if isinstance(payload, dict):
            self.events.append(payload)


def test_native_lifecycle_and_qos_visibility(actions, proc_info):
    assert len(actions) == len(EXPECTED_NODES)
    rclpy.init()
    node = rclpy.create_node('native_lifecycle_qos_validation_probe')
    collector = _Collector()
    node.create_subscription(String, '/inspection/events', collector.on_event, 50)
    probe = NativeLifecycleProbe(node)
    deadline = time.time() + 8.0
    try:
        while time.time() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            active_nodes = {str(item.get('node', '')) for item in collector.events if str(item.get('lifecycle_state', '')) == 'ACTIVE'}
            if active_nodes.issuperset(EXPECTED_NODES):
                break
        active_nodes = {str(item.get('node', '')) for item in collector.events if str(item.get('lifecycle_state', '')) == 'ACTIVE'}
        for expected in EXPECTED_NODES:
            assert expected in active_nodes
        if probe.enabled:
            for expected in EXPECTED_NODES:
                assert probe.wait_for_state(expected, 'ACTIVE', timeout_sec=1.0)
                assert probe.get_available_transitions(expected)
    finally:
        node.destroy_node()
        rclpy.shutdown()
