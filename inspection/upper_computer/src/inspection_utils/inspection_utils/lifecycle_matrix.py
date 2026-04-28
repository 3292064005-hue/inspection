from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from inspection_supervisor.lifecycle_graph import load_runtime_topology


@dataclass(frozen=True, slots=True)
class LifecycleGovernanceSpec:
    """Describe how a runtime node participates in lifecycle governance.

    Attributes:
        node: Canonical node name.
        governance_class: One of ``native_required``, ``bridge_allowed``, or
            ``standard_node``.
        lifecycle_mode: Expected runtime lifecycle mode.
        rationale: Short explanation for the assigned governance class.
        fault_domain: Recovery / diagnostics fault domain label.
        lifecycle_managed: Whether the node can receive lifecycle commands.
        supervisor_monitored: Whether the node is tracked by the supervisor
            health registry.
    """

    node: str
    governance_class: str
    lifecycle_mode: str
    rationale: str
    fault_domain: str
    lifecycle_managed: bool
    supervisor_monitored: bool

    def to_dict(self) -> dict[str, str | bool]:
        return {
            'node': self.node,
            'governanceClass': self.governance_class,
            'lifecycleMode': self.lifecycle_mode,
            'rationale': self.rationale,
            'faultDomain': self.fault_domain,
            'lifecycleManaged': self.lifecycle_managed,
            'supervisorMonitored': self.supervisor_monitored,
        }


_NODE_ALIASES = {
    'fsm_node': 'inspection_fsm_node',
    'vision_camera_node': 'camera_node',
    'inspection_hmi_gateway_node': 'inspection_hmi_gateway_server',
}


@lru_cache(maxsize=1)
def _governance_specs() -> tuple[LifecycleGovernanceSpec, ...]:
    return tuple(
        LifecycleGovernanceSpec(
            node=spec.name,
            governance_class=spec.governance_class,
            lifecycle_mode=spec.lifecycle_mode,
            rationale=spec.rationale,
            fault_domain=spec.fault_domain,
            lifecycle_managed=spec.lifecycle_managed,
            supervisor_monitored=spec.supervisor_monitored,
        )
        for spec in load_runtime_topology()
    )



def normalize_governed_node_name(node_name: str) -> str:
    """Normalize runtime node names to the canonical governance matrix keys."""
    normalized = str(node_name or '').strip()
    return _NODE_ALIASES.get(normalized, normalized)



def lifecycle_governance_matrix() -> list[dict[str, str | bool]]:
    """Return the lifecycle governance matrix for diagnostics and tests."""
    return [spec.to_dict() for spec in _governance_specs()]



def lifecycle_governance_for(node_name: str) -> dict[str, str | bool] | None:
    """Lookup lifecycle governance for a specific node name or alias."""
    name = normalize_governed_node_name(node_name)
    for spec in _governance_specs():
        if spec.node == name:
            return spec.to_dict()
    return None



def governance_class_for(node_name: str) -> str:
    """Return the governance class for a node or ``standard_node`` by default."""
    governance = lifecycle_governance_for(node_name)
    return str(governance.get('governanceClass', 'standard_node')) if isinstance(governance, dict) else 'standard_node'



def requires_native_lifecycle(node_name: str) -> bool:
    """Return ``True`` when a node must not fall back to topic lifecycle control."""
    return governance_class_for(node_name) == 'native_required'



def allows_lifecycle_fallback(node_name: str) -> bool:
    """Return ``True`` only for nodes explicitly governed by the compatibility bridge."""
    return governance_class_for(node_name) == 'bridge_allowed'



def is_standard_node(node_name: str) -> bool:
    """Return ``True`` when the node should not receive lifecycle transitions."""
    return governance_class_for(node_name) == 'standard_node'



def governed_node_names() -> list[str]:
    """Return the ordered list of known lifecycle-governed nodes."""
    return [spec.node for spec in _governance_specs()]
