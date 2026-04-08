from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from inspection_diagnostics.diagnostics_aggregator import DiagnosticsAggregator
from inspection_diagnostics.subscription_policy import diagnostics_subscription_policy


def test_diagnostics_subscription_policy_defaults_disable_annotated_stream() -> None:
    policy = diagnostics_subscription_policy(False)
    assert policy == {
        'camera_status': True,
        'result_raw': True,
        'annotated_image': False,
    }


def test_diagnostics_subscription_policy_can_enable_annotated_stream() -> None:
    policy = diagnostics_subscription_policy(True)
    assert policy['camera_status'] is True
    assert policy['result_raw'] is True
    assert policy['annotated_image'] is True


def test_diagnostics_aggregator_marks_annotated_stream_disabled_by_default() -> None:
    agg = DiagnosticsAggregator()
    snap = agg.build_snapshot()
    channel = snap['channels']['annotated_stream']
    assert channel['level'] == 'OK'
    assert channel['values']['enabled'] is False
    assert channel['values']['available'] is False
    assert channel['values']['frameCount'] == 0


def test_diagnostics_aggregator_tracks_annotated_stream_when_enabled() -> None:
    agg = DiagnosticsAggregator()
    agg.set_annotated_stream_enabled(True)
    agg.ingest_annotated_frame({'frameId': 'frame-1', 'width': 320, 'height': 240, 'encoding': 'bgr8'})
    snap = agg.build_snapshot()
    channel = snap['channels']['annotated_stream']
    assert channel['level'] == 'OK'
    assert channel['values']['enabled'] is True
    assert channel['values']['available'] is True
    assert channel['values']['frameId'] == 'frame-1'
    assert channel['values']['frameCount'] == 1


def test_inspection_diagnostics_package_declares_sensor_msgs_dependency() -> None:
    root = Path(__file__).resolve().parents[2]
    package_xml = root / 'src' / 'inspection_diagnostics' / 'package.xml'
    setup_py = (root / 'src' / 'inspection_diagnostics' / 'setup.py').read_text(encoding='utf-8')

    tree = ET.fromstring(package_xml.read_text(encoding='utf-8'))
    exec_depends = {elem.text for elem in tree.findall('exec_depend')}

    assert 'sensor_msgs' in exec_depends
    assert "'sensor_msgs'" in setup_py


def test_runtime_docs_describe_annotated_diagnostics_gate() -> None:
    root = Path(__file__).resolve().parents[2]
    upper_readme = (root / 'README.md').read_text(encoding='utf-8')
    top_readme = (root.parent / 'README.md').read_text(encoding='utf-8')
    offline_launch = (root / 'src' / 'inspection_bringup' / 'launch' / 'offline_replay.launch.py').read_text(encoding='utf-8')
    real_launch = (root / 'src' / 'inspection_bringup' / 'launch' / 'real_station.launch.py').read_text(encoding='utf-8')

    for text in (upper_readme, top_readme, offline_launch, real_launch):
        assert 'enable_annotated_image_diagnostics' in text
