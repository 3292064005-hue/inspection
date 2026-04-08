from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .replay_executor import ReplayExecutor


@dataclass(slots=True)
class RegressionCase:
    trace_id: str
    changed: bool
    diff: dict[str, Any]


class RegressionRunner:
    def __init__(self, root: Path) -> None:
        self.executor = ReplayExecutor(root)

    def run(self, trace_ids: list[str] | None = None) -> list[RegressionCase]:
        selected = trace_ids or self.executor.list_traces()
        results: list[RegressionCase] = []
        for trace_id in selected:
            diff = self.executor.compare_trace_to_summary(trace_id)
            changed = bool(diff.get('changed', False))
            results.append(RegressionCase(trace_id=trace_id, changed=changed, diff=diff))
        return results
