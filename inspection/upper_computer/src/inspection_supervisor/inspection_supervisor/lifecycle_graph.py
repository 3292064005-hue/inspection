from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ManagedNodeSpec:
    name: str
    stage: str
    startup_order: int
    required: bool = True


DEFAULT_LIFECYCLE_GRAPH: tuple[ManagedNodeSpec, ...] = (
    ManagedNodeSpec('station_bridge_node', 'core_io', 10),
    ManagedNodeSpec('camera_node', 'sensing', 20),
    ManagedNodeSpec('vision_processor_node', 'processing', 30),
    ManagedNodeSpec('decision_node', 'processing', 40),
    ManagedNodeSpec('inspection_fsm_node', 'control', 50),
    ManagedNodeSpec('inspection_logger_node', 'support', 60),
    ManagedNodeSpec('inspection_diagnostics_node', 'support', 70, required=False),
)


def ordered_startup(graph: tuple[ManagedNodeSpec, ...] = DEFAULT_LIFECYCLE_GRAPH) -> list[str]:
    return [node.name for node in sorted(graph, key=lambda item: item.startup_order)]


def ordered_shutdown(graph: tuple[ManagedNodeSpec, ...] = DEFAULT_LIFECYCLE_GRAPH) -> list[str]:
    return list(reversed(ordered_startup(graph)))
