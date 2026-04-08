from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class OwnershipCheck:
    ok: bool
    reason: str = ''


def _safe_int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except Exception:
        return default


def current_trace_active(trace_id: str) -> bool:
    return bool(str(trace_id or '').strip())


def check_binding(expected_trace_id: str, expected_item_id: int, payload: dict[str, Any], *, allow_missing_trace: bool = False) -> OwnershipCheck:
    actual_trace_id = str(payload.get('trace_id', '') or '')
    actual_item_id = _safe_int(payload.get('item_id', -1), -1)
    if not current_trace_active(expected_trace_id):
        return OwnershipCheck(False, 'no_active_trace')
    if actual_trace_id:
        if actual_trace_id != expected_trace_id:
            return OwnershipCheck(False, f'trace_id_mismatch:{actual_trace_id}')
    elif not allow_missing_trace:
        return OwnershipCheck(False, 'missing_trace_id')
    if actual_item_id != expected_item_id:
        return OwnershipCheck(False, f'item_id_mismatch:{actual_item_id}')
    return OwnershipCheck(True, '')


def check_station_detail(expected_trace_id: str, expected_item_id: int, detail: dict[str, Any]) -> OwnershipCheck:
    # Bridge state events may omit trace_id during global states such as HEARTBEAT/CAPABILITIES.
    # For item-scoped states, item_id must match when provided.
    if not current_trace_active(expected_trace_id):
        return OwnershipCheck(True, '')
    return check_binding(expected_trace_id, expected_item_id, detail, allow_missing_trace=True)
