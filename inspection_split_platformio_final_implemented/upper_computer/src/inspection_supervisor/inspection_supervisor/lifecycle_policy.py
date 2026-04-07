from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from inspection_utils.lifecycle_matrix import is_standard_node, normalize_governed_node_name

from .mode_manager import SupervisorMode


@dataclass(frozen=True, slots=True)
class LifecycleAction:
    action: str
    node: str = ''
    reason: str = ''
    stage: str = ''

    def to_dict(self) -> dict[str, str]:
        payload = {'action': self.action}
        if self.node:
            payload['node'] = self.node
        if self.reason:
            payload['reason'] = self.reason
        if self.stage:
            payload['stage'] = self.stage
        return payload


def build_lifecycle_plan(*, ordered_nodes: Iterable[str], health: dict[str, object], mode: str) -> list[dict[str, str]]:
    """Build the next lifecycle action plan for the governed runtime graph.

    Standard nodes are treated as heartbeat/data-source participants and are not
    sent lifecycle transitions. Nodes classified as ``native_required`` or
    ``bridge_allowed`` continue through configure/activate actions.
    """
    node_map = health.get('nodes', {}) if isinstance(health, dict) else {}
    progress = health.get('activation_progress', {}) if isinstance(health, dict) else {}
    actions: list[LifecycleAction] = []
    for raw_name in ordered_nodes:
        name = normalize_governed_node_name(raw_name)
        snapshot = node_map.get(name, node_map.get(raw_name, {})) if isinstance(node_map, dict) else {}
        state = str(snapshot.get('state', 'UNKNOWN')).upper()
        healthy = bool(snapshot.get('healthy', False))
        active = bool(snapshot.get('active', False))
        if not healthy:
            actions.append(LifecycleAction('await_heartbeat', node=name, reason='node_not_healthy'))
            break
        if is_standard_node(name):
            if not active:
                actions.append(LifecycleAction('await_activation', node=name, reason='standard_node_not_active'))
                break
            continue
        if state in {'UNKNOWN', 'UNCONFIGURED', 'INIT'}:
            actions.append(LifecycleAction('configure_node', node=name, reason='lifecycle_prepare'))
            break
        if state in {'INACTIVE', 'CONFIGURED'}:
            actions.append(LifecycleAction('activate_node', node=name, reason='lifecycle_activate'))
            break
        if not active:
            actions.append(LifecycleAction('await_activation', node=name, reason='node_not_active'))
            break
    if not actions and int(progress.get('required', 0)) and int(progress.get('active', 0)) >= int(progress.get('required', 0)):
        actions.append(LifecycleAction('stack_active', stage=SupervisorMode(str(mode).upper()).value))
    return [action.to_dict() for action in actions]
