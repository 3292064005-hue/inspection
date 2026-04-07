from inspection_logger.cycle_summary_builder import TraceAccumulator


def test_cycle_summary_builder_collects_result_and_finish():
    acc = TraceAccumulator(trace_id='TRACE-1')
    acc.ingest({
        'type': 'inspection_result',
        'trace_id': 'TRACE-1',
        'batch_id': 'B1',
        'item_id': 1,
        'detail': {'evidence': {'raw_path': 'raw.png', 'annotated_path': 'ann.png'}},
    })
    acc.ingest({
        'type': 'cycle_finish',
        'trace_id': 'TRACE-1',
        'batch_id': 'B1',
        'item_id': 1,
        'decision': 'OK',
        'cycle_time_sec': 1.23,
        'phase_timings_ms': {'analyze_wait': 120.0},
    })
    summary = acc.to_summary()
    assert summary['decision'] == 'OK'
    assert summary['image_paths']['raw'] == 'raw.png'
