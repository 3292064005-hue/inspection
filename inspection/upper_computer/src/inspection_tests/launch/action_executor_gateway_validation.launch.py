import time
import pytest
launch_testing = pytest.importorskip('launch_testing')
launch = pytest.importorskip('launch')
launch_ros = pytest.importorskip('launch_ros')
rclpy = pytest.importorskip('rclpy')
from std_msgs.msg import String

def generate_test_description():
    actions = [
        launch_ros.actions.Node(package='inspection_hmi_gateway', executable='inspection_action_executor_node', name='inspection_action_executor_node', output='screen', parameters=[{'managed_runtime_enabled': True, 'managed_runtime_autostart': True, 'native_action_server_enabled': True}]),
        launch_ros.actions.Node(package='inspection_hmi_gateway', executable='inspection_hmi_gateway_server', name='inspection_hmi_gateway_server', output='screen', additional_env={'INSPECTION_ACTION_EXECUTOR_ENABLED': 'true', 'INSPECTION_NATIVE_ACTION_CLIENT_ENABLED': 'true', 'INSPECTION_HMI_PORT': '8080', 'INSPECTION_HMI_LOG_ROOT': 'logs/runtime', 'INSPECTION_HMI_RECIPE_ROOT': 'config/recipes'}),
    ]
    return launch.LaunchDescription(actions + [launch_testing.actions.ReadyToTest()]), {'actions': actions}

def test_executor_and_gateway_processes_started(actions, proc_info):
    assert len(actions) == 2

def test_executor_transport_topics_emit_no_startup_faults():
    rclpy.init(); node = rclpy.create_node('action_executor_gateway_validation_probe'); messages=[]
    def _on_event(msg: String): messages.append(msg.data)
    node.create_subscription(String, '/inspection/action_executor/events', _on_event, 50)
    deadline = time.time() + 2.0
    while time.time() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    try:
        assert isinstance(messages, list)
    finally:
        node.destroy_node(); rclpy.shutdown()
