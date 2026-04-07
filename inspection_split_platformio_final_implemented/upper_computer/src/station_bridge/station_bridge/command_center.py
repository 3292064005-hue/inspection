from __future__ import annotations

from dataclasses import dataclass, field

from .ack_tracker import AckTracker, PendingCommand


@dataclass(slots=True)
class CommandCenter:
    tracker: AckTracker = field(default_factory=AckTracker)
    active_generation: int = 1

    def rollover_session(self, generation: int) -> list[PendingCommand]:
        self.active_generation = generation
        return self.tracker.invalidate_other_generations(generation)

    def register(self, seq: int, command_name: str, trace_id: str, item_id: int, batch_id: str, retry_index: int = 0) -> PendingCommand:
        return self.tracker.register(seq, command_name, trace_id, item_id, batch_id, retry_index=retry_index, session_generation=self.active_generation)

    def resolve(self, seq: int) -> PendingCommand | None:
        return self.tracker.get(seq, session_generation=self.active_generation)

    def snapshot(self) -> list[dict[str, object]]:
        return self.tracker.snapshot()
