from __future__ import annotations

from .node_health_registry import NodeHealthRegistry


def startup_actions(registry: NodeHealthRegistry, ordered_nodes: list[str]) -> list[dict[str, object]]:
    actions: list[dict[str, object]] = []
    for name in ordered_nodes:
        node = registry.nodes.get(name)
        if node is None or not node.active:
            actions.append({'action': 'await_node', 'node': name})
    if not actions:
        actions.append({'action': 'stack_ready'})
    return actions
