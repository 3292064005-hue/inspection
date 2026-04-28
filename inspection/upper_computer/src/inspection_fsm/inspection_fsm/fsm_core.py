from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .cancellation_policy import can_cancel
from .guard_rules import guard_allows


class StationPhase(str, Enum):
    BOOT = 'BOOT'
    IDLE = 'IDLE'
    SELF_CHECK = 'SELF_CHECK'
    READY = 'READY'
    FEED_WAIT_ACK = 'FEED_WAIT_ACK'
    POSITION_WAIT = 'POSITION_WAIT'
    CAPTURE_WAIT_FRAME = 'CAPTURE_WAIT_FRAME'
    ANALYZE_WAIT = 'ANALYZE_WAIT'
    DECISION_WAIT = 'DECISION_WAIT'
    SORT_WAIT_ACK = 'SORT_WAIT_ACK'
    SORT_WAIT_DONE = 'SORT_WAIT_DONE'
    COUNT_UPDATE = 'COUNT_UPDATE'
    PAUSED = 'PAUSED'
    MANUAL_MODE = 'MANUAL_MODE'
    RECOVERING = 'RECOVERING'
    FAULT = 'FAULT'
    ESTOP_LOCKED = 'ESTOP_LOCKED'


class StationEvent(str, Enum):
    START = 'START'
    RESET = 'RESET'
    SELF_CHECK_OK = 'SELF_CHECK_OK'
    FEED_REQUESTED = 'FEED_REQUESTED'
    FEED_ACK = 'FEED_ACK'
    POSITION_READY = 'POSITION_READY'
    CAPTURE_DONE = 'CAPTURE_DONE'
    RESULT_READY = 'RESULT_READY'
    DECISION_READY = 'DECISION_READY'
    SORT_ACK = 'SORT_ACK'
    SORT_DONE = 'SORT_DONE'
    TIMEOUT = 'TIMEOUT'
    FAULT = 'FAULT'
    ESTOP = 'ESTOP'
    PAUSE = 'PAUSE'
    RESUME = 'RESUME'
    ENTER_MANUAL = 'ENTER_MANUAL'
    EXIT_MANUAL = 'EXIT_MANUAL'
    CANCEL_ITEM = 'CANCEL_ITEM'
    CANCEL = 'CANCEL_ITEM'
    MANUAL_STEP_FEED = 'MANUAL_STEP_FEED'
    MANUAL_STEP_CAPTURE = 'MANUAL_STEP_CAPTURE'
    MANUAL_STEP_SORT = 'MANUAL_STEP_SORT'
    HEARTBEAT_LOST = 'HEARTBEAT_LOST'
    RECOVERY_OK = 'RECOVERY_OK'
    RECOVERY_FAIL = 'RECOVERY_FAIL'


@dataclass(slots=True)
class FSMData:
    phase: StationPhase = StationPhase.BOOT
    item_id: int = 0
    batch_id: str = ''
    recipe_id: str = ''
    cycle_index: int = 0
    last_reason: str = ''
    trace_id: str = ''
    retry_counts: dict[str, int] = field(default_factory=dict)
    last_event: str = ''
    resume_phase: StationPhase | None = None
    manual_mode_enabled: bool = False
    last_fault_code: str = ''
    heartbeat_ok: bool = True


@dataclass(slots=True)
class TransitionResult:
    changed: bool
    next_phase: StationPhase
    reason: str
    commands: list[str] = field(default_factory=list)


def _advance_trace_id(data: FSMData) -> None:
    data.trace_id = f'{data.batch_id}-{data.item_id:05d}-C{data.cycle_index:03d}'


def start_cycle(data: FSMData) -> None:
    data.cycle_index += 1
    _advance_trace_id(data)
    data.retry_counts.clear()


def finish_cycle(data: FSMData) -> None:
    data.item_id += 1
    data.trace_id = ''
    data.retry_counts.clear()
    data.resume_phase = None


def clear_cycle_runtime(data: FSMData) -> None:
    data.trace_id = ''
    data.retry_counts.clear()
    data.resume_phase = None


def phase_timeout_key(phase: StationPhase) -> str:
    mapping = {
        StationPhase.FEED_WAIT_ACK: 'feed_timeout_sec',
        StationPhase.POSITION_WAIT: 'position_timeout_sec',
        StationPhase.CAPTURE_WAIT_FRAME: 'capture_frame_timeout_sec',
        StationPhase.ANALYZE_WAIT: 'analyze_timeout_sec',
        StationPhase.DECISION_WAIT: 'decision_timeout_sec',
        StationPhase.SORT_WAIT_ACK: 'sort_ack_timeout_sec',
        StationPhase.SORT_WAIT_DONE: 'sort_done_timeout_sec',
        StationPhase.RECOVERING: 'recovery_timeout_sec',
    }
    return mapping.get(phase, '')


def _same_phase_command_result(data: FSMData, reason: str, commands: list[str]) -> TransitionResult:
    data.last_reason = reason
    return TransitionResult(True, data.phase, reason, commands=commands)


def transition(data: FSMData, event: StationEvent, detail: str = '') -> TransitionResult:
    data.last_event = event.value
    phase = data.phase
    allowed, guard_reason = guard_allows(data, event)
    if not allowed:
        return TransitionResult(False, phase, f'guard:{guard_reason}')

    if event == StationEvent.ESTOP:
        data.phase = StationPhase.ESTOP_LOCKED
        data.last_reason = detail or 'estop'
        data.last_fault_code = data.last_reason
        data.resume_phase = None
        return TransitionResult(True, data.phase, data.last_reason, commands=['clear_cycle'])

    if event in {StationEvent.FAULT, StationEvent.HEARTBEAT_LOST}:
        data.phase = StationPhase.FAULT
        data.last_reason = detail or ('heartbeat_lost' if event == StationEvent.HEARTBEAT_LOST else 'fault')
        data.last_fault_code = data.last_reason
        data.heartbeat_ok = event != StationEvent.HEARTBEAT_LOST
        data.resume_phase = None
        return TransitionResult(True, data.phase, data.last_reason)

    if event == StationEvent.PAUSE and phase not in {StationPhase.PAUSED, StationPhase.FAULT, StationPhase.ESTOP_LOCKED, StationPhase.RECOVERING}:
        data.resume_phase = phase
        data.phase = StationPhase.PAUSED
        data.last_reason = detail or 'pause'
        return TransitionResult(True, data.phase, data.last_reason)

    if phase == StationPhase.PAUSED and event == StationEvent.RESUME:
        data.phase = data.resume_phase or StationPhase.READY
        data.last_reason = detail or 'resume'
        data.resume_phase = None
        return TransitionResult(True, data.phase, data.last_reason)

    if phase in {StationPhase.FAULT, StationPhase.ESTOP_LOCKED}:
        if event == StationEvent.RESET:
            data.phase = StationPhase.RECOVERING
            data.last_reason = detail or 'reset'
            data.resume_phase = None
            return TransitionResult(True, data.phase, data.last_reason, commands=['clear_cycle', 'publish_reset'])
        return TransitionResult(False, phase, 'ignored_in_locked_phase')

    if phase == StationPhase.RECOVERING and event == StationEvent.RECOVERY_OK:
        data.phase = StationPhase.SELF_CHECK
        data.last_reason = detail or 'recovery_ok'
        data.last_fault_code = ''
        data.heartbeat_ok = True
        return TransitionResult(True, data.phase, data.last_reason)

    if phase == StationPhase.RECOVERING and event == StationEvent.RECOVERY_FAIL:
        data.phase = StationPhase.FAULT
        data.last_reason = detail or 'recovery_failed'
        data.last_fault_code = data.last_reason
        return TransitionResult(True, data.phase, data.last_reason)

    if event == StationEvent.CANCEL:
        if not can_cancel(phase):
            return TransitionResult(False, phase, 'cancel_not_allowed')
        data.phase = StationPhase.READY
        data.last_reason = detail or 'cancel_item'
        return TransitionResult(True, data.phase, data.last_reason, commands=['clear_cycle', 'start_cycle'])

    if phase in (StationPhase.BOOT, StationPhase.IDLE) and event == StationEvent.START:
        data.phase = StationPhase.SELF_CHECK
        data.last_reason = detail or 'start'
        return TransitionResult(True, data.phase, data.last_reason, commands=['clear_cycle'])

    if phase == StationPhase.SELF_CHECK and event == StationEvent.SELF_CHECK_OK:
        data.phase = StationPhase.READY
        data.last_reason = detail or 'self_check_ok'
        return TransitionResult(True, data.phase, data.last_reason, commands=['start_cycle'])

    if phase == StationPhase.READY and event == StationEvent.ENTER_MANUAL:
        data.phase = StationPhase.MANUAL_MODE
        data.manual_mode_enabled = True
        data.last_reason = detail or 'enter_manual'
        return TransitionResult(True, data.phase, data.last_reason)

    if phase == StationPhase.MANUAL_MODE and event == StationEvent.EXIT_MANUAL:
        data.phase = StationPhase.READY
        data.manual_mode_enabled = False
        data.last_reason = detail or 'exit_manual'
        return TransitionResult(True, data.phase, data.last_reason, commands=['clear_cycle', 'start_cycle'])

    if phase == StationPhase.MANUAL_MODE and event == StationEvent.MANUAL_STEP_FEED:
        return _same_phase_command_result(data, detail or 'manual_feed', ['publish_feed'])

    if phase == StationPhase.MANUAL_MODE and event == StationEvent.MANUAL_STEP_CAPTURE:
        return _same_phase_command_result(data, detail or 'manual_capture', ['publish_capture'])

    if phase == StationPhase.MANUAL_MODE and event == StationEvent.MANUAL_STEP_SORT:
        return _same_phase_command_result(data, detail or 'manual_sort', ['publish_sort'])

    if phase == StationPhase.READY and event == StationEvent.FEED_REQUESTED:
        data.phase = StationPhase.FEED_WAIT_ACK
        data.last_reason = detail or 'feed_requested'
        return TransitionResult(True, data.phase, data.last_reason, commands=['publish_feed'])

    if phase == StationPhase.FEED_WAIT_ACK and event == StationEvent.FEED_ACK:
        data.phase = StationPhase.POSITION_WAIT
        data.last_reason = detail or 'feed_ack'
        return TransitionResult(True, data.phase, data.last_reason)

    if phase == StationPhase.POSITION_WAIT and event == StationEvent.POSITION_READY:
        data.phase = StationPhase.CAPTURE_WAIT_FRAME
        data.last_reason = detail or 'position_ready'
        return TransitionResult(True, data.phase, data.last_reason, commands=['publish_capture'])

    if phase == StationPhase.CAPTURE_WAIT_FRAME and event == StationEvent.CAPTURE_DONE:
        data.phase = StationPhase.ANALYZE_WAIT
        data.last_reason = detail or 'capture_done'
        return TransitionResult(True, data.phase, data.last_reason)

    if phase == StationPhase.ANALYZE_WAIT and event == StationEvent.RESULT_READY:
        data.phase = StationPhase.DECISION_WAIT
        data.last_reason = detail or 'result_ready'
        return TransitionResult(True, data.phase, data.last_reason)

    if phase == StationPhase.DECISION_WAIT and event == StationEvent.DECISION_READY:
        data.phase = StationPhase.SORT_WAIT_ACK
        data.last_reason = detail or 'decision_ready'
        return TransitionResult(True, data.phase, data.last_reason, commands=['publish_sort'])

    if phase == StationPhase.SORT_WAIT_ACK and event == StationEvent.SORT_ACK:
        data.phase = StationPhase.SORT_WAIT_DONE
        data.last_reason = detail or 'sort_ack'
        return TransitionResult(True, data.phase, data.last_reason)

    if phase == StationPhase.SORT_WAIT_DONE and event == StationEvent.SORT_DONE:
        data.phase = StationPhase.COUNT_UPDATE
        data.last_reason = detail or 'sort_done'
        return TransitionResult(True, data.phase, data.last_reason, commands=['finish_cycle'])

    if phase == StationPhase.COUNT_UPDATE and event == StationEvent.START:
        data.phase = StationPhase.READY
        data.last_reason = detail or 'next_cycle'
        return TransitionResult(True, data.phase, data.last_reason, commands=['start_cycle'])

    if event == StationEvent.TIMEOUT:
        data.phase = StationPhase.FAULT
        data.last_reason = detail or f'timeout:{phase.value}'
        data.last_fault_code = data.last_reason
        return TransitionResult(True, data.phase, data.last_reason)

    return TransitionResult(False, phase, f'ignored:{phase.value}:{event.value}')


def advance_on_bridge(data: FSMData, bridge_state: str) -> StationPhase:
    bridge_state = (bridge_state or '').upper()
    mapping = {
        'FEED_ACK': StationEvent.FEED_ACK,
        'POSITION_READY': StationEvent.POSITION_READY,
        'SORT_ACK': StationEvent.SORT_ACK,
        'SORT_DONE': StationEvent.SORT_DONE,
        'FAULT': StationEvent.FAULT,
        'HEARTBEAT_LOST': StationEvent.HEARTBEAT_LOST,
        'RESET_ACK': StationEvent.RECOVERY_OK,
    }
    event = mapping.get(bridge_state)
    if not event:
        return data.phase
    return transition(data, event, f'bridge:{bridge_state}').next_phase
