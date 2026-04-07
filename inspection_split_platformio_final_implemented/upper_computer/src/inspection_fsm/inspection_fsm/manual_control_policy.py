from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .fsm_core import StationEvent


ALLOWED_MANUAL_EVENT_VALUES = {
    'MANUAL_STEP_FEED',
    'MANUAL_STEP_CAPTURE',
    'MANUAL_STEP_SORT',
}


def allowed_manual_step(event: 'StationEvent') -> bool:
    return getattr(event, 'value', str(event)) in ALLOWED_MANUAL_EVENT_VALUES
