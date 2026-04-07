from pathlib import Path


def test_logger_cleanup_converts_bag_stop_failure_to_runtime_event() -> None:
    root = Path(__file__).resolve().parents[2]
    text = (root / 'src' / 'inspection_logger' / 'inspection_logger' / 'logger_node.py').read_text(encoding='utf-8')
    assert 'def _stop_bag_recording' in text
    assert 'bag_recording_stop_failed' in text
    assert "self._stop_bag_recording('logger_cleanup')" in text
    assert "self._stop_bag_recording('logger_shutdown')" in text
