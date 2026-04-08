from __future__ import annotations

from typing import Any


def diff_summaries(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    keys = sorted(set(left) | set(right))
    changed: dict[str, dict[str, Any]] = {}
    for key in keys:
        if left.get(key) != right.get(key):
            changed[key] = {'left': left.get(key), 'right': right.get(key)}
    return {
        'trace_id': right.get('trace_id') or left.get('trace_id', ''),
        'changed_keys': sorted(changed),
        'changes': changed,
    }
