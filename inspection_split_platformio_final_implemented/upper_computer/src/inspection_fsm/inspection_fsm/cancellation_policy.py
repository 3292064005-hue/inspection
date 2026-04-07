from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .fsm_core import StationPhase


CANCELLABLE_PHASE_VALUES = {
    'READY',
    'FEED_WAIT_ACK',
    'POSITION_WAIT',
    'CAPTURE_WAIT_FRAME',
    'ANALYZE_WAIT',
    'DECISION_WAIT',
    'SORT_WAIT_ACK',
    'SORT_WAIT_DONE',
    'PAUSED',
}


def can_cancel(phase: 'StationPhase') -> bool:
    return getattr(phase, 'value', str(phase)) in CANCELLABLE_PHASE_VALUES
