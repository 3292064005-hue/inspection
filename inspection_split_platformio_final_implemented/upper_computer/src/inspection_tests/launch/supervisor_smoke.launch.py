import pytest

launch_testing = pytest.importorskip('launch_testing')
launch = pytest.importorskip('launch')
launch_ros = pytest.importorskip('launch_ros')


def generate_test_description():
    node = launch_ros.actions.Node(
        package='inspection_supervisor',
        executable='supervisor_node',
        name='inspection_supervisor_node',
        output='screen',
    )
    return launch.LaunchDescription([node, launch_testing.actions.ReadyToTest()]), {'node': node}


def test_supervisor_process_starts(node, proc_info):
    """Verify the supervisor process reaches startup during launch testing.

    Args:
        node: Launch action for the supervisor node under test.
        proc_info: launch_testing process information helper.

    Returns:
        None.

    Raises:
        AssertionError: If the launched process never reaches the startup state.

    Boundary behavior:
        The assertion only checks process startup and does not require a full
        ROS graph probe, keeping the smoke test lightweight while still proving
        the executable can be launched by the runtime.
    """

    assert node is not None
    proc_info.assertWaitForStartup(process=node, timeout=5.0)
