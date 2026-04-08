from inspection_logger.replay_validator import validate_trace_events
from inspection_logger.diff_reporter import diff_summaries


def test_validate_trace_events_flags_missing_terminal():
    report = validate_trace_events('TRACE-1', [{'type': 'capture_request'}, {'type': 'inspection_result'}, {'type': 'sort_command'}])
    assert report.valid is False
    assert 'trace_has_no_terminal_event' in report.warnings


def test_diff_summaries_reports_changed_keys():
    diff = diff_summaries({'trace_id': 'TRACE-1', 'decision': 'OK'}, {'trace_id': 'TRACE-1', 'decision': 'NG'})
    assert 'decision' in diff['changed_keys']
