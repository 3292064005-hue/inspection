from pathlib import Path

from inspection_logger.defaults import CORE_BAG_TOPICS, DEFAULT_BAG_TOPICS, DIAGNOSTIC_BAG_TOPICS, core_bag_topics, default_bag_topics, diagnostic_bag_topics


def test_logger_cleanup_converts_bag_stop_failure_to_runtime_event() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_logger' / 'inspection_logger' / 'logger_node.py').read_text(encoding='utf-8')
    assert 'def _stop_bag_recording' in text
    assert 'bag_recording_stop_failed' in text
    assert "self._stop_bag_recording('logger_cleanup')" in text
    assert "self._stop_bag_recording('logger_shutdown')" in text


def test_logger_default_bag_topics_match_core_production_publishers() -> None:
    expected_core = [
        '/inspection/image_raw',
        '/inspection/result',
        '/inspection/camera/status',
        '/inspection/capture_request',
        '/inspection/decision_output',
        '/station/sort_request',
        '/station/state',
        '/station/count_stats',
        '/station/fault',
        '/inspection/events',
    ]
    expected_diagnostics = [
        '/inspection/image_annotated',
        '/inspection/result_raw',
        '/inspection/diagnostics',
    ]
    assert CORE_BAG_TOPICS == expected_core
    assert core_bag_topics() == expected_core
    assert DIAGNOSTIC_BAG_TOPICS == expected_diagnostics
    assert diagnostic_bag_topics() == expected_diagnostics
    assert DEFAULT_BAG_TOPICS == expected_core
    assert default_bag_topics() == expected_core
    assert '/station/sort_cmd' not in expected_core
