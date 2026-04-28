from inspection_logger.replay_validator import validate_trace_events


def test_validate_trace_events_marks_missing_terminal_event_as_warning() -> None:
    report = validate_trace_events('TRACE-1', [
        {'type': 'capture_request', 'event_layer': 'normalized'},
        {'type': 'inspection_result', 'event_layer': 'normalized'},
        {'type': 'decision_output', 'event_layer': 'normalized'},
        {'type': 'sort_request', 'event_layer': 'normalized'},
    ])
    assert report.valid is False
    assert report.missing_types == []
    assert 'trace_has_no_terminal_event' in report.warnings
    assert 'trace_has_no_public_projection_events' in report.warnings


def test_validate_trace_events_counts_public_projection_layer() -> None:
    report = validate_trace_events('TRACE-2', [
        {'type': 'capture_request', 'event_layer': 'normalized'},
        {'type': 'inspection_result', 'event_layer': 'normalized'},
        {'type': 'decision_output', 'event_layer': 'normalized'},
        {'type': 'sort_request', 'event_layer': 'normalized'},
        {'type': 'public_projection', 'event_layer': 'public_projection', 'public_type': 'inspection.result.finalized'},
        {'type': 'cycle_finish', 'event_layer': 'normalized'},
    ])
    assert report.valid is True
    assert report.public_projection_count == 1
    assert 'trace_has_no_public_projection_events' not in report.warnings
