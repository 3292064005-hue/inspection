from __future__ import annotations

from dataclasses import dataclass

from inspection_utils.transport_common import (
    CANCEL_COMMAND,
    ENTER_MANUAL_COMMAND,
    EXIT_MANUAL_COMMAND,
    MANUAL_STEP_CAPTURE_COMMAND,
    MANUAL_STEP_FEED_COMMAND,
    MANUAL_STEP_SORT_COMMAND,
    PAUSE_COMMAND,
    RESET_COMMAND,
    RESUME_COMMAND,
    START_COMMAND,
    STOP_COMMAND,
    normalize_control_command,
)

from .fsm_core import StationEvent


@dataclass(frozen=True, slots=True)
class ControlDispatch:
    """Normalized control command dispatch decision for the FSM boundary.

    Attributes:
        command: Canonical control command string after alias normalization.
        event: FSM event to emit for the command.
        compatibility_mode: Whether the mapping preserves a legacy semantic bridge.
        detail_reason: Diagnostic reason suffix to persist in FSM event history.
    """

    command: str
    event: StationEvent
    compatibility_mode: bool = False
    detail_reason: str = ''


_CONTROL_DISPATCH_TABLE: dict[str, ControlDispatch] = {
    PAUSE_COMMAND: ControlDispatch(command=PAUSE_COMMAND, event=StationEvent.PAUSE, detail_reason='control:pause'),
    STOP_COMMAND: ControlDispatch(
        command=STOP_COMMAND,
        event=StationEvent.PAUSE,
        compatibility_mode=True,
        detail_reason='control:stop_compat_pause',
    ),
    RESUME_COMMAND: ControlDispatch(command=RESUME_COMMAND, event=StationEvent.RESUME, detail_reason='control:resume'),
    CANCEL_COMMAND: ControlDispatch(command=CANCEL_COMMAND, event=StationEvent.CANCEL, detail_reason='control:cancel'),
    ENTER_MANUAL_COMMAND: ControlDispatch(command=ENTER_MANUAL_COMMAND, event=StationEvent.ENTER_MANUAL, detail_reason='control:enter_manual'),
    EXIT_MANUAL_COMMAND: ControlDispatch(command=EXIT_MANUAL_COMMAND, event=StationEvent.EXIT_MANUAL, detail_reason='control:exit_manual'),
    MANUAL_STEP_FEED_COMMAND: ControlDispatch(command=MANUAL_STEP_FEED_COMMAND, event=StationEvent.MANUAL_STEP_FEED, detail_reason='control:manual_step_feed'),
    MANUAL_STEP_CAPTURE_COMMAND: ControlDispatch(command=MANUAL_STEP_CAPTURE_COMMAND, event=StationEvent.MANUAL_STEP_CAPTURE, detail_reason='control:manual_step_capture'),
    MANUAL_STEP_SORT_COMMAND: ControlDispatch(command=MANUAL_STEP_SORT_COMMAND, event=StationEvent.MANUAL_STEP_SORT, detail_reason='control:manual_step_sort'),
    RESET_COMMAND: ControlDispatch(command=RESET_COMMAND, event=StationEvent.RESET, detail_reason='control:reset'),
    START_COMMAND: ControlDispatch(command=START_COMMAND, event=StationEvent.START, detail_reason='control:start'),
}


def dispatch_control_command(command: str | None) -> ControlDispatch | None:
    """Resolve a control command to the FSM event contract.

    Args:
        command: Raw control command string from gateway, supervisor, or another transport.

    Returns:
        A :class:`ControlDispatch` record when the command is known; otherwise ``None``.
    """
    normalized = normalize_control_command(command)
    return _CONTROL_DISPATCH_TABLE.get(normalized)
