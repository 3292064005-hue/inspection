from __future__ import annotations

from inspection_logger.bag_manager import BagManager


def test_bag_manager_builds_record_command() -> None:
    manager = BagManager(ros2_executable='ros2')
    cmd = manager.build_record_command(output_path='bags/run1', topics=['/a', '/b'])
    assert cmd[:4] == ['ros2', 'bag', 'record', '-o']
    assert '-s' in cmd
    assert 'mcap' in cmd
    assert cmd[-2:] == ['/a', '/b']


def test_bag_manager_builds_play_command() -> None:
    manager = BagManager(ros2_executable='ros2')
    cmd = manager.build_play_command(bag_path='bags/run1', paused=True, rate=2.0)
    assert '--start-paused' in cmd
    assert '--storage' in cmd
    assert 'mcap' in cmd
    assert cmd[0:3] == ['ros2', 'bag', 'play']


def test_bag_manager_builds_info_command() -> None:
    manager = BagManager(ros2_executable='ros2')
    cmd = manager.build_info_command(bag_path='bags/run1')
    assert cmd == ['ros2', 'bag', 'info', 'bags/run1']


def test_bag_manager_builds_record_command_with_storage_config() -> None:
    manager = BagManager(ros2_executable='ros2', storage_config_uri='config/system/rosbag_mcap_writer.yaml')
    cmd = manager.build_record_command(output_path='bags/run2', topics=['/x'], storage_config_uri='config/system/rosbag_mcap_writer.yaml')
    assert '--storage-config-file' in cmd
    assert 'config/system/rosbag_mcap_writer.yaml' in cmd
