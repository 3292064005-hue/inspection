from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .artifact_registry import ArtifactRegistry


@dataclass(slots=True)
class CycleRuntime:
    cycle_index: int = 0
    trace_id: str = ''
    item_id: int = -1
    batch_id: str = ''
    recipe_id: str = ''
    current_phase: str = ''
    last_fault_code: str = ''
    latest_result: dict[str, Any] = field(default_factory=dict)
    latest_decision: dict[str, Any] = field(default_factory=dict)
    pending_commands: list[dict[str, Any]] = field(default_factory=list)
    phase_timings_ms: dict[str, float] = field(default_factory=dict)
    retry_counts: dict[str, int] = field(default_factory=dict)
    artifacts: ArtifactRegistry = field(default_factory=ArtifactRegistry)

    def bind(self, *, cycle_index: int, trace_id: str, item_id: int, batch_id: str, recipe_id: str = '') -> None:
        self.cycle_index = cycle_index
        self.trace_id = trace_id
        self.item_id = item_id
        self.batch_id = batch_id
        self.recipe_id = recipe_id
        self.current_phase = ''
        self.last_fault_code = ''
        self.latest_result.clear()
        self.latest_decision.clear()
        self.pending_commands.clear()
        self.phase_timings_ms.clear()
        self.retry_counts.clear()
        self.artifacts.clear()

    def clear(self) -> None:
        self.bind(cycle_index=0, trace_id='', item_id=-1, batch_id='', recipe_id='')

    def attach_result(self, detail: dict[str, Any]) -> None:
        self.latest_result = dict(detail)
        evidence = detail.get('evidence')
        if isinstance(evidence, dict):
            for key in ('raw_path', 'annotated_path'):
                if key in evidence:
                    self.artifacts.set(key, evidence[key])

    def attach_decision(self, detail: dict[str, Any]) -> None:
        self.latest_decision = dict(detail)

    def update_pending_commands(self, snapshot: list[dict[str, Any]]) -> None:
        self.pending_commands = [dict(item) for item in snapshot]

    def snapshot(self) -> dict[str, Any]:
        return {
            'cycle_index': self.cycle_index,
            'trace_id': self.trace_id,
            'item_id': self.item_id,
            'batch_id': self.batch_id,
            'recipe_id': self.recipe_id,
            'current_phase': self.current_phase,
            'last_fault_code': self.last_fault_code,
            'latest_result': dict(self.latest_result),
            'latest_decision': dict(self.latest_decision),
            'pending_commands': [dict(item) for item in self.pending_commands],
            'phase_timings_ms': dict(self.phase_timings_ms),
            'retry_counts': dict(self.retry_counts),
            'artifacts': self.artifacts.snapshot(),
        }
