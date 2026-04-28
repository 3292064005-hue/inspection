from __future__ import annotations

from typing import Any

from .mode_manager import SupervisorMode



def _domain_node_map(fault_domains: dict[str, Any] | None, key: str) -> dict[str, list[str]]:
    domains = fault_domains or {}
    mapped: dict[str, list[str]] = {}
    for domain_name, payload in domains.items():
        if not isinstance(payload, dict):
            continue
        nodes = [str(item) for item in payload.get(key, []) if str(item).strip()]
        if nodes:
            mapped[str(domain_name)] = sorted(nodes)
    return mapped



def build_recovery_plan(
    *,
    healthy: bool,
    stale_nodes: list[str],
    missing_active_nodes: list[str],
    current_mode: str,
    fault_domains: dict[str, Any] | None = None,
) -> list[dict[str, object]]:
    """Build a scope-aware supervisor recovery plan.

    Args:
        healthy: Current aggregate health status.
        stale_nodes: Required nodes considered stale.
        missing_active_nodes: Required nodes not in an active state.
        current_mode: Supervisor mode string.
        fault_domains: Optional domain-indexed health summary from the
            supervisor registry.

    Returns:
        Ordered recovery actions. When domain information is available, restart
        and reactivate actions are grouped by fault domain to reduce recovery
        blast radius.
    """
    if healthy:
        return [{'action': 'noop'}]
    mode = SupervisorMode(current_mode)
    plan: list[dict[str, object]] = []
    if mode == SupervisorMode.AUTO:
        plan.append({'action': 'pause_auto'})

    stale_by_domain = _domain_node_map(fault_domains, 'staleNodes')
    missing_by_domain = _domain_node_map(fault_domains, 'missingActiveNodes')

    if stale_by_domain:
        for domain_name, nodes in stale_by_domain.items():
            plan.append({'action': 'restart_nodes', 'fault_domain': domain_name, 'nodes': nodes})
    elif stale_nodes:
        plan.append({'action': 'restart_nodes', 'nodes': list(stale_nodes)})

    if missing_by_domain:
        for domain_name, nodes in missing_by_domain.items():
            plan.append({'action': 'reactivate_nodes', 'fault_domain': domain_name, 'nodes': nodes})
    elif missing_active_nodes:
        plan.append({'action': 'reactivate_nodes', 'nodes': list(missing_active_nodes)})

    degraded_domains = sorted(set(stale_by_domain) | set(missing_by_domain))
    if degraded_domains:
        plan.append({'action': 'request_fault_domain_review', 'fault_domains': degraded_domains})
    plan.append({'action': 'request_reset_if_faulted'})
    return plan
