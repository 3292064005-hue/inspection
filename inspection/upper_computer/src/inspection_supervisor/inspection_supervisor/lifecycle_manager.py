from __future__ import annotations

from dataclasses import dataclass, field

from .lifecycle_clients import LifecycleCommand, lifecycle_command_from_plan_item
from .lifecycle_executor import LifecycleExecutor
from .lifecycle_policy import build_lifecycle_plan
from .node_health_registry import NodeHealthRegistry


@dataclass(slots=True)
class LifecycleManager:
    ordered_nodes: list[str]
    last_plan: list[dict[str, str]] = field(default_factory=list)
    executor: LifecycleExecutor = field(default_factory=LifecycleExecutor)

    def evaluate(self, registry: NodeHealthRegistry, *, now: float, timeout_sec: float, mode: str) -> dict[str, object]:
        health = registry.overall_status(now=now, timeout_sec=timeout_sec)
        self.last_plan = build_lifecycle_plan(ordered_nodes=self.ordered_nodes, health=health, mode=mode)
        next_command = self.executor.next_command(self.last_plan)
        return {
            'health': health,
            'lifecycle_plan': list(self.last_plan),
            'next_lifecycle_command': next_command.to_dict() if next_command else {},
            'executor': self.executor.snapshot(),
        }

    def mark_dispatched(self, command: dict[str, object]) -> None:
        signature = str(command.get('signature', ''))
        if not signature:
            return
        for planned in self.executor.plan_commands(self.last_plan):
            if planned.signature == signature:
                self.executor.mark_dispatched(planned)
                return

    def resolve_command(self, command: dict[str, object]) -> LifecycleCommand:
        signature = str(command.get('signature', ''))
        for planned in self.executor.plan_commands(self.last_plan):
            if planned.signature == signature:
                return planned
        transition = str(command.get('transition', 'ACTIVATE')).upper() or 'ACTIVATE'
        action_map = {
            'CONFIGURE': 'configure_node',
            'ACTIVATE': 'activate_node',
            'DEACTIVATE': 'deactivate_node',
            'CLEANUP': 'cleanup_node',
            'SHUTDOWN': 'shutdown_node',
        }
        resolved = lifecycle_command_from_plan_item({'action': action_map.get(transition, ''), 'node': str(command.get('node', '')), 'reason': str(command.get('reason', '')), 'stage': str(command.get('stage', ''))})
        if resolved is None:
            target_state = str(command.get('target_state', transition)).upper()
            return LifecycleCommand(node=str(command.get('node', '')), transition=transition, target_state=target_state, reason=str(command.get('reason', '')), stage=str(command.get('stage', '')))
        return resolved
