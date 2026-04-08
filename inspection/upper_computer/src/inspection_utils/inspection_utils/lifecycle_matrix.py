from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LifecycleGovernanceSpec:
    """Describe how a runtime node participates in lifecycle governance.

    Attributes:
        node: Canonical node name.
        governance_class: One of ``native_required``, ``bridge_allowed``, or
            ``standard_node``.
        lifecycle_mode: Expected runtime lifecycle mode.
        rationale: Short explanation for the assigned governance class.
    """

    node: str
    governance_class: str
    lifecycle_mode: str
    rationale: str

    def to_dict(self) -> dict[str, str]:
        return {
            'node': self.node,
            'governanceClass': self.governance_class,
            'lifecycleMode': self.lifecycle_mode,
            'rationale': self.rationale,
        }


LIFECYCLE_GOVERNANCE_MATRIX: tuple[LifecycleGovernanceSpec, ...] = (
    LifecycleGovernanceSpec('inspection_supervisor_node', 'native_required', 'native_service_only', 'supervisor must coordinate explicit node transitions and recovery'),
    LifecycleGovernanceSpec('inspection_hmi_gateway_node', 'bridge_allowed', 'managed_runtime', 'gateway can operate with compatibility bridge while still exposing lifecycle state'),
    LifecycleGovernanceSpec('inspection_action_executor_node', 'native_required', 'native_service_only', 'executor owns long-running action transport and should expose native lifecycle transitions'),
    LifecycleGovernanceSpec('vision_processor_node', 'bridge_allowed', 'managed_runtime', 'vision processing must gate capture/analyze flow on lifecycle activation'),
    LifecycleGovernanceSpec('inspection_diagnostics_node', 'bridge_allowed', 'managed_runtime', 'diagnostics should continue publishing governance state even without native lifecycle support'),
    LifecycleGovernanceSpec('station_bridge_node', 'bridge_allowed', 'managed_runtime', 'device bridge must participate in recovery while supporting lightweight test environments'),
    LifecycleGovernanceSpec('inspection_orchestrator_node', 'bridge_allowed', 'managed_runtime', 'orchestrator should follow managed mode transitions driven by the supervisor'),
    LifecycleGovernanceSpec('inspection_fsm_node', 'bridge_allowed', 'managed_runtime', 'FSM owns cycle semantics and should remain transition-aware even under compatibility mode'),
    LifecycleGovernanceSpec('camera_node', 'bridge_allowed', 'managed_runtime', 'camera transport should still participate in startup ordering when a managed wrapper is present'),
    LifecycleGovernanceSpec('inspection_hmi_node', 'standard_node', 'best_effort', 'standalone HMI shell remains a standard utility node'),
)

_NODE_ALIASES = {
    'fsm_node': 'inspection_fsm_node',
    'vision_camera_node': 'camera_node',
}


def normalize_governed_node_name(node_name: str) -> str:
    """Normalize runtime node names to the canonical governance matrix keys."""
    normalized = str(node_name or '').strip()
    return _NODE_ALIASES.get(normalized, normalized)


def lifecycle_governance_matrix() -> list[dict[str, str]]:
    """Return the lifecycle governance matrix for diagnostics and tests."""
    return [spec.to_dict() for spec in LIFECYCLE_GOVERNANCE_MATRIX]


def lifecycle_governance_for(node_name: str) -> dict[str, str] | None:
    """Lookup lifecycle governance for a specific node name or alias."""
    name = normalize_governed_node_name(node_name)
    for spec in LIFECYCLE_GOVERNANCE_MATRIX:
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
    return [spec.node for spec in LIFECYCLE_GOVERNANCE_MATRIX]
