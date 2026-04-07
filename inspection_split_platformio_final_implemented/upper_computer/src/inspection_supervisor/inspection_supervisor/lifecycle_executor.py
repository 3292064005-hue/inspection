from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .lifecycle_clients import LifecycleCommand, lifecycle_command_from_plan_item


@dataclass(slots=True)
class LifecycleExecutor:
    last_dispatched_signature: str = ''
    dispatch_history: list[str] = field(default_factory=list)

    def plan_commands(self, lifecycle_plan: list[dict[str, Any]]) -> list[LifecycleCommand]:
        commands: list[LifecycleCommand] = []
        for item in lifecycle_plan:
            if not isinstance(item, dict):
                continue
            command = lifecycle_command_from_plan_item(item)
            if command is not None:
                commands.append(command)
        return commands

    def next_command(self, lifecycle_plan: list[dict[str, Any]]) -> LifecycleCommand | None:
        for command in self.plan_commands(lifecycle_plan):
            if command.signature != self.last_dispatched_signature:
                return command
        return None

    def mark_dispatched(self, command: LifecycleCommand) -> None:
        self.last_dispatched_signature = command.signature
        self.dispatch_history.append(command.signature)
        self.dispatch_history = self.dispatch_history[-100:]

    def reset(self) -> None:
        self.last_dispatched_signature = ''

    def snapshot(self) -> dict[str, Any]:
        return {
            'last_dispatched_signature': self.last_dispatched_signature,
            'dispatch_history': list(self.dispatch_history[-20:]),
        }
