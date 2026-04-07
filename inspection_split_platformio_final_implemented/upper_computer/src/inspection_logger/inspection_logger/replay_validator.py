from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REQUIRED_TRACE_TYPES = {
    'capture_request',
    'inspection_result',
    'sort_command',
}


@dataclass(slots=True)
class ValidationReport:
    trace_id: str
    valid: bool
    missing_types: list[str]
    final_type: str
    event_count: int
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            'trace_id': self.trace_id,
            'valid': self.valid,
            'missing_types': list(self.missing_types),
            'final_type': self.final_type,
            'event_count': self.event_count,
            'warnings': list(self.warnings),
        }


def validate_trace_events(trace_id: str, events: list[dict[str, Any]]) -> ValidationReport:
    types_seen = {str(event.get('type', '')) for event in events}
    missing = [name for name in sorted(REQUIRED_TRACE_TYPES) if name not in types_seen]
    warnings: list[str] = []
    final_type = str(events[-1].get('type', '')) if events else ''
    if final_type not in {'cycle_finish', 'fault'}:
        warnings.append('trace_has_no_terminal_event')
    if 'fsm_drop_result' in types_seen or 'fsm_drop_capture_event' in types_seen:
        warnings.append('trace_contains_dropped_payload_events')
    return ValidationReport(
        trace_id=trace_id,
        valid=not missing and final_type in {'cycle_finish', 'fault'},
        missing_types=missing,
        final_type=final_type,
        event_count=len(events),
        warnings=warnings,
    )
