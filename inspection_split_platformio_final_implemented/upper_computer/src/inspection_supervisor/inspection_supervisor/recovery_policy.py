from __future__ import annotations

from .mode_manager import SupervisorMode


def build_recovery_plan(*, healthy: bool, stale_nodes: list[str], missing_active_nodes: list[str], current_mode: str) -> list[dict[str, object]]:
    if healthy:
        return [{'action': 'noop'}]
    mode = SupervisorMode(current_mode)
    plan: list[dict[str, object]] = []
    if mode == SupervisorMode.AUTO:
        plan.append({'action': 'pause_auto'})
    if stale_nodes:
        plan.append({'action': 'restart_nodes', 'nodes': stale_nodes})
    if missing_active_nodes:
        plan.append({'action': 'reactivate_nodes', 'nodes': missing_active_nodes})
    plan.append({'action': 'request_reset_if_faulted'})
    return plan
