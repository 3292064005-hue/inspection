from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inspection_utils.config_common import load_yaml
from inspection_utils.io_common import resolve_runtime_path

DEFAULT_LIFECYCLE_GRAPH_PATH = 'config/system/lifecycle_graph.yaml'


@dataclass(frozen=True, slots=True)
class ManagedNodeSpec:
    """Runtime-topology node specification.

    The historical module name is kept for import compatibility, but the
    payload now represents the full runtime topology rather than only
    lifecycle-managed nodes.
    """

    name: str
    stage: str
    startup_order: int
    required: bool = True
    criticality: str = 'required'
    fault_domain: str = 'support'
    lifecycle_managed: bool = True
    supervisor_monitored: bool = True
    governance_class: str = 'bridge_allowed'
    lifecycle_mode: str = 'managed_runtime'
    rationale: str = ''

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'stage': self.stage,
            'startupOrder': self.startup_order,
            'required': self.required,
            'criticality': self.criticality,
            'faultDomain': self.fault_domain,
            'lifecycleManaged': self.lifecycle_managed,
            'supervisorMonitored': self.supervisor_monitored,
            'governanceClass': self.governance_class,
            'lifecycleMode': self.lifecycle_mode,
            'rationale': self.rationale,
        }


DEFAULT_RUNTIME_TOPOLOGY: tuple[ManagedNodeSpec, ...] = (
    ManagedNodeSpec('station_bridge_node', 'core_io', 10, criticality='critical', fault_domain='io'),
    ManagedNodeSpec('camera_node', 'sensing', 20, fault_domain='vision'),
    ManagedNodeSpec('vision_processor_node', 'processing', 30, fault_domain='vision'),
    ManagedNodeSpec('decision_node', 'processing', 40, fault_domain='decision'),
    ManagedNodeSpec('inspection_fsm_node', 'control', 50, criticality='critical', fault_domain='decision'),
    ManagedNodeSpec('inspection_logger_node', 'support', 60, fault_domain='quality'),
    ManagedNodeSpec('inspection_diagnostics_node', 'support', 70, required=False, criticality='optional', fault_domain='quality'),
    ManagedNodeSpec('inspection_action_executor_node', 'control', 80, fault_domain='actuation', governance_class='native_required', lifecycle_mode='native_service_only'),
    ManagedNodeSpec('inspection_orchestrator_node', 'control', 90, fault_domain='actuation'),
    ManagedNodeSpec('inspection_hmi_gateway_server', 'hmi', 100, required=False, criticality='optional', fault_domain='gateway', lifecycle_managed=False, supervisor_monitored=False, governance_class='standard_node', lifecycle_mode='external_service'),
    ManagedNodeSpec('inspection_hmi_node', 'hmi', 110, required=False, criticality='optional', fault_domain='gateway', lifecycle_managed=False, supervisor_monitored=False, governance_class='standard_node', lifecycle_mode='best_effort'),
    ManagedNodeSpec('inspection_supervisor_node', 'control', 120, criticality='critical', fault_domain='control', lifecycle_managed=False, supervisor_monitored=False, governance_class='standard_node', lifecycle_mode='best_effort'),
)
DEFAULT_LIFECYCLE_GRAPH: tuple[ManagedNodeSpec, ...] = tuple(spec for spec in DEFAULT_RUNTIME_TOPOLOGY if spec.lifecycle_managed)


def _spec_from_mapping(payload: dict[str, Any]) -> ManagedNodeSpec:
    lifecycle_managed = bool(payload.get('lifecycle_managed', payload.get('lifecycleManaged', True)))
    governance_class = str(payload.get('governance_class', payload.get('governanceClass', 'bridge_allowed')) or 'bridge_allowed')
    lifecycle_mode = str(payload.get('lifecycle_mode', payload.get('lifecycleMode', 'managed_runtime')) or 'managed_runtime')
    supervisor_monitored_default = lifecycle_managed
    return ManagedNodeSpec(
        name=str(payload.get('name', '')).strip(),
        stage=str(payload.get('stage', 'support')).strip() or 'support',
        startup_order=int(payload.get('startup_order', payload.get('startupOrder', 0)) or 0),
        required=bool(payload.get('required', True)),
        criticality=str(payload.get('criticality', 'required') or ('required' if bool(payload.get('required', True)) else 'optional')),
        fault_domain=str(payload.get('fault_domain', payload.get('faultDomain', 'support')) or 'support'),
        lifecycle_managed=lifecycle_managed,
        supervisor_monitored=bool(payload.get('supervisor_monitored', payload.get('supervisorMonitored', supervisor_monitored_default))),
        governance_class=governance_class,
        lifecycle_mode=lifecycle_mode,
        rationale=str(payload.get('rationale', '') or ''),
    )



def load_runtime_topology(path: str = DEFAULT_LIFECYCLE_GRAPH_PATH) -> tuple[ManagedNodeSpec, ...]:
    """Load the runtime-topology configuration from disk.

    Args:
        path: Runtime-relative configuration path.

    Returns:
        Ordered runtime-topology specs exactly as declared in configuration.

    Raises:
        FileNotFoundError: When the configured topology file does not exist.
        ValueError: When the topology payload is malformed, empty, or contains
            duplicate node names.

    Boundary behavior:
        The loader accepts both the legacy ``managed_nodes`` key and the newer
        ``runtime_nodes`` key so existing assets can migrate without schema
        drift at import time.
    """
    resolved = resolve_runtime_path(path, start=__file__)
    if not resolved.exists():
        raise FileNotFoundError(f'lifecycle graph is required: {resolved}')
    payload = load_yaml(resolved) or {}
    items = []
    if isinstance(payload, dict):
        items = payload.get('runtime_nodes', payload.get('runtimeNodes', payload.get('managed_nodes', payload.get('managedNodes', [])))) or []
    if not isinstance(items, list) or not items:
        raise ValueError('lifecycle graph runtime_nodes must be a non-empty list')
    graph: list[ManagedNodeSpec] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('lifecycle graph item must be a mapping')
        spec = _spec_from_mapping(item)
        if not spec.name:
            raise ValueError('lifecycle graph item name is required')
        if spec.name in seen:
            raise ValueError(f'duplicate lifecycle graph node: {spec.name}')
        seen.add(spec.name)
        graph.append(spec)
    return tuple(graph)



def load_lifecycle_graph(path: str = DEFAULT_LIFECYCLE_GRAPH_PATH) -> tuple[ManagedNodeSpec, ...]:
    """Load the lifecycle-managed subset from the runtime topology."""
    return tuple(spec for spec in load_runtime_topology(path) if spec.lifecycle_managed)



def monitored_topology(path: str = DEFAULT_LIFECYCLE_GRAPH_PATH) -> tuple[ManagedNodeSpec, ...]:
    """Return the supervisor-monitored subset of the runtime topology."""
    return tuple(spec for spec in load_runtime_topology(path) if spec.supervisor_monitored)



def ordered_startup(graph: tuple[ManagedNodeSpec, ...] = DEFAULT_LIFECYCLE_GRAPH) -> list[str]:
    return [node.name for node in sorted(graph, key=lambda item: item.startup_order)]



def ordered_shutdown(graph: tuple[ManagedNodeSpec, ...] = DEFAULT_LIFECYCLE_GRAPH) -> list[str]:
    return list(reversed(ordered_startup(graph)))



def ordered_monitored_startup(topology: tuple[ManagedNodeSpec, ...] = DEFAULT_RUNTIME_TOPOLOGY) -> list[str]:
    """Return supervisor-monitored nodes ordered by startup rank."""
    monitored = tuple(spec for spec in topology if spec.supervisor_monitored)
    return ordered_startup(monitored)
