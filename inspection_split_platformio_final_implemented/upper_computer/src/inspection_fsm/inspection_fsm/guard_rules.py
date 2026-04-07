from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .fsm_core import FSMData, StationEvent, StationPhase


ACTIVE_PHASE_VALUES = {
    'FEED_WAIT_ACK',
    'POSITION_WAIT',
    'CAPTURE_WAIT_FRAME',
    'ANALYZE_WAIT',
    'DECISION_WAIT',
    'SORT_WAIT_ACK',
    'SORT_WAIT_DONE',
}

MANUAL_EVENT_VALUES = {
    'MANUAL_STEP_FEED',
    'MANUAL_STEP_CAPTURE',
    'MANUAL_STEP_SORT',
}


def requires_active_item(phase: 'StationPhase') -> bool:
    return getattr(phase, 'value', str(phase)) in ACTIVE_PHASE_VALUES


def guard_allows(data: 'FSMData', event: 'StationEvent') -> tuple[bool, str]:
    event_value = getattr(event, 'value', str(event))
    phase_value = getattr(data.phase, 'value', str(data.phase))
    if event_value == 'RESUME':
        if phase_value != 'PAUSED' or data.resume_phase is None:
            return False, 'resume_without_pause'
    if event_value in MANUAL_EVENT_VALUES and phase_value != 'MANUAL_MODE':
        return False, 'manual_event_without_manual_mode'
    if event_value == 'CAPTURE_DONE' and phase_value != 'CAPTURE_WAIT_FRAME':
        return False, 'capture_done_outside_capture_wait'
    if event_value == 'RESULT_READY' and phase_value != 'ANALYZE_WAIT':
        return False, 'result_ready_outside_analyze_wait'
    if event_value == 'DECISION_READY' and phase_value != 'DECISION_WAIT':
        return False, 'decision_ready_outside_decision_wait'
    if event_value in {'SORT_ACK', 'SORT_DONE'} and not data.trace_id:
        return False, 'sort_event_without_active_trace'
    if requires_active_item(data.phase) and event_value not in {
        'TIMEOUT',
        'FAULT',
        'ESTOP',
        'PAUSE',
        'CANCEL_ITEM',
        'HEARTBEAT_LOST',
    }:
        if not data.trace_id:
            return False, 'active_phase_without_trace_id'
    return True, ''
