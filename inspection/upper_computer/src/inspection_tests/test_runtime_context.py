from inspection_fsm.runtime_context import RuntimeContext


def test_runtime_context_tracks_cycle_state():
    runtime = RuntimeContext(profile_name='debug')
    runtime.current.bind(cycle_index=2, trace_id='TRACE-2', item_id=7, batch_id='B1')
    runtime.current.current_phase = 'ANALYZE_WAIT'
    runtime.current.attach_result({'trace_id': 'TRACE-2', 'item_id': 7, 'evidence': {'raw_path': 'a.png'}})
    runtime.record_manual_action('manual_step_capture', trace_id='TRACE-2', item_id=7)
    snap = runtime.snapshot()
    assert snap['profile_name'] == 'debug'
    assert snap['current']['trace_id'] == 'TRACE-2'
    assert snap['current']['artifacts']['raw_path'] == 'a.png'
    assert snap['manual_history'][0]['action'] == 'manual_step_capture'
