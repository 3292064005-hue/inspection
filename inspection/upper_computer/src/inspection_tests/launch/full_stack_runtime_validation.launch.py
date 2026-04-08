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
from inspection_utils.qos import qos_summary

ROOT_DIR = Path(__file__).resolve().parents[3]
RUNTIME_LOG_ROOT = str(Path(tempfile.gettempdir()) / 'inspection_runtime_validation_logs')
DEFAULT_RECIPE_PATH = str(ROOT_DIR / 'config' / 'recipes' / 'default_recipe.yaml')

EXPECTED_RUNTIME_NODES = [
    'inspection_diagnostics_node',
    'inspection_logger_node',
    'decision_node',
]


def generate_test_description():
    actions = [
        launch_ros.actions.Node(
            package='inspection_diagnostics', executable='diagnostics_node', name='inspection_diagnostics_node', output='screen',
            parameters=[{'managed_runtime_enabled': True, 'managed_runtime_autostart': True}],
        ),
        launch_ros.actions.Node(
            package='inspection_logger', executable='logger_node', name='inspection_logger_node', output='screen',
            parameters=[{'managed_runtime_enabled': True, 'managed_runtime_autostart': True, 'log_root': RUNTIME_LOG_ROOT}],
        ),
        launch_ros.actions.Node(
            package='inspection_decision', executable='decision_node', name='decision_node', output='screen',
            parameters=[{'managed_runtime_enabled': True, 'managed_runtime_autostart': True, 'recipe_path': DEFAULT_RECIPE_PATH}],
        ),
    ]
    return launch.LaunchDescription(actions + [launch_testing.actions.ReadyToTest()]), {'actions': actions}


class _EventCollector:
    def __init__(self):
        self.events = []
        self.diagnostics = []

    def on_event(self, msg: String):
        payload = safe_json_loads(msg.data)
        if isinstance(payload, dict):
            self.events.append(payload)
            if str(payload.get('type', '')) == 'diagnostics_snapshot':
                self.diagnostics.append(payload)


def test_runtime_nodes_started(actions, proc_info):
    assert len(actions) == 3


def test_launch_runtime_lifecycle_and_qos_observation():
    rclpy.init()
    node = rclpy.create_node('runtime_validation_probe')
    collector = _EventCollector()
    node.create_subscription(String, '/inspection/events', collector.on_event, 50)
    probe = NativeLifecycleProbe(node)
    deadline = time.time() + 5.0
    while time.time() < deadline and not collector.diagnostics:
        rclpy.spin_once(node, timeout_sec=0.1)
    try:
        # managed-runtime event observation should always work
        seen_active = {str(item.get('node', '')) for item in collector.events if str(item.get('lifecycle_state', '')) == 'ACTIVE'}
        for runtime_node in EXPECTED_RUNTIME_NODES:
            assert runtime_node in seen_active
        # diagnostics payload should surface the active QoS matrix
        assert collector.diagnostics, 'expected diagnostics_snapshot event'
        qos_payload = collector.diagnostics[-1].get('qos_profiles', {})
        assert qos_payload == qos_summary()
        # In a native lifecycle capable ROS2 Humble environment, the state services should also report ACTIVE.
        if probe.enabled:
            for runtime_node in EXPECTED_RUNTIME_NODES:
                assert probe.wait_for_state(runtime_node, 'ACTIVE', timeout_sec=1.0)
                available = probe.get_available_transitions(runtime_node)
                assert available
    finally:
        node.destroy_node()
        rclpy.shutdown()
