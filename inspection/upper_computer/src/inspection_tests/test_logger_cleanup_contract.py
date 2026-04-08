from pathlib import Path

from inspection_logger.defaults import DEFAULT_BAG_TOPICS, default_bag_topics


def test_logger_cleanup_converts_bag_stop_failure_to_runtime_event() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_logger' / 'inspection_logger' / 'logger_node.py').read_text(encoding='utf-8')
    assert 'def _stop_bag_recording' in text
    assert 'bag_recording_stop_failed' in text
    assert "self._stop_bag_recording('logger_cleanup')" in text
    assert "self._stop_bag_recording('logger_shutdown')" in text



def test_logger_default_bag_topics_match_live_publishers() -> None:
    expected = [
        '/inspection/image_raw',
        '/inspection/image_annotated',
        '/inspection/result',
        '/inspection/result_raw',
        '/inspection/camera/status',
        '/inspection/capture_request',
        '/station/sort_cmd',
        '/station/state',
        '/station/count_stats',
        '/station/fault',
        '/inspection/events',
        '/inspection/diagnostics',
    ]
    assert DEFAULT_BAG_TOPICS == expected
    assert default_bag_topics() == expected
    assert '/inspection/decision/final' not in expected
