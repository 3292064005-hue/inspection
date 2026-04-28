from inspection_fsm.fsm_core import FSMData, StationEvent, StationPhase, advance_on_bridge, start_cycle, transition


def test_advance_from_feed_ack_to_position_wait():
    data = FSMData(phase=StationPhase.FEED_WAIT_ACK, trace_id='TRACE-1')
    assert advance_on_bridge(data, 'FEED_ACK') == StationPhase.POSITION_WAIT


def test_happy_path_transition_sequence_v5():
    data = FSMData(phase=StationPhase.IDLE)
    assert transition(data, StationEvent.START, 'boot').next_phase == StationPhase.SELF_CHECK
    assert transition(data, StationEvent.SELF_CHECK_OK, 'selfcheck').next_phase == StationPhase.READY
    start_cycle(data)
    assert transition(data, StationEvent.FEED_REQUESTED, 'feed').next_phase == StationPhase.FEED_WAIT_ACK
    assert transition(data, StationEvent.FEED_ACK, 'ack').next_phase == StationPhase.POSITION_WAIT
    assert transition(data, StationEvent.POSITION_READY, 'sensor').next_phase == StationPhase.CAPTURE_WAIT_FRAME
    assert transition(data, StationEvent.CAPTURE_DONE, 'frame').next_phase == StationPhase.ANALYZE_WAIT
    assert transition(data, StationEvent.RESULT_READY, 'result').next_phase == StationPhase.DECISION_WAIT
    assert transition(data, StationEvent.DECISION_READY, 'decision').next_phase == StationPhase.SORT_WAIT_ACK
    assert transition(data, StationEvent.SORT_ACK, 'sort_ack').next_phase == StationPhase.SORT_WAIT_DONE
    assert transition(data, StationEvent.SORT_DONE, 'done').next_phase == StationPhase.COUNT_UPDATE


def test_fault_reset_goes_through_recovering():
    data = FSMData(phase=StationPhase.FAULT)
    result = transition(data, StationEvent.RESET, 'reset')
    assert result.next_phase == StationPhase.RECOVERING
    assert 'clear_cycle' in result.commands
    assert 'publish_reset' in result.commands


def test_pause_resume_roundtrip():
    data = FSMData(phase=StationPhase.POSITION_WAIT, trace_id='TRACE-1')
    assert transition(data, StationEvent.PAUSE, 'pause').next_phase == StationPhase.PAUSED
    assert transition(data, StationEvent.RESUME, 'resume').next_phase == StationPhase.POSITION_WAIT


def test_manual_mode_and_manual_step():
    data = FSMData(phase=StationPhase.READY)
    assert transition(data, StationEvent.ENTER_MANUAL, 'manual').next_phase == StationPhase.MANUAL_MODE
    step = transition(data, StationEvent.MANUAL_STEP_FEED, 'feed')
    assert step.next_phase == StationPhase.MANUAL_MODE
    assert 'publish_feed' in step.commands


def test_cancel_item_returns_ready_and_restarts_cycle():
    data = FSMData(phase=StationPhase.ANALYZE_WAIT, trace_id='TRACE-1')
    result = transition(data, StationEvent.CANCEL_ITEM, 'cancel')
    assert result.next_phase == StationPhase.READY
    assert result.commands == ['clear_cycle', 'start_cycle']


def test_fsm_data_defaults_do_not_invent_gateway_binding():
    data = FSMData()
    assert data.batch_id == ''
    assert data.recipe_id == ''
