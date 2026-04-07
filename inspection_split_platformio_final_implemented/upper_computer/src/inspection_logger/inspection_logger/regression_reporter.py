from __future__ import annotations

from typing import Iterable, Any

from .regression_runner import RegressionCase


def build_regression_report(cases: Iterable[RegressionCase]) -> dict[str, Any]:
    items = list(cases)
    changed = [case for case in items if case.changed]
    return {
        'total': len(items),
        'changed': len(changed),
        'unchanged': len(items) - len(changed),
        'changed_traces': [case.trace_id for case in changed],
        'results': [
            {
                'trace_id': case.trace_id,
                'changed': case.changed,
                'diff': case.diff,
            }
            for case in items
        ],
    }
