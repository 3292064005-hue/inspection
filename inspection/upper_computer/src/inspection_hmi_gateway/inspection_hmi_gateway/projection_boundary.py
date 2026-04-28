from __future__ import annotations

"""Authoritative boundary descriptors for gateway runtime/query projections."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProjectionBoundaryDescriptor:
    name: str
    owner: str
    purpose: str
    event_sources: tuple[str, ...]
    storage_surface: str
    repair_strategy: str
    query_surface: str

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'owner': self.owner,
            'purpose': self.purpose,
            'eventSources': list(self.event_sources),
            'storageSurface': self.storage_surface,
            'repairStrategy': self.repair_strategy,
            'querySurface': self.query_surface,
        }


RUNTIME_PROJECTION_BOUNDARY = ProjectionBoundaryDescriptor(
    name='runtime_projection',
    owner='inspection_hmi_gateway.runtime_projection',
    purpose='Drive websocket/HMI runtime state and short-lived result correlation.',
    event_sources=(
        'inspection.result.observed',
        'inspection.result.finalized',
        'station.state.updated',
        'station.count.updated',
        'orchestrator.advice',
    ),
    storage_surface='in_memory_gateway_state',
    repair_strategy='replay_from_live_runtime_only',
    query_surface='websocket_runtime_snapshot',
)

QUERY_PROJECTION_BOUNDARY = ProjectionBoundaryDescriptor(
    name='query_projection',
    owner='inspection_logger.read_model_writer',
    purpose='Serve durable result, replay, export, and statistics queries.',
    event_sources=(
        'result_log.csv',
        'summary.jsonl',
        'replay_manifest.jsonl',
        'artifacts_index.jsonl',
        'read_model.sqlite3',
    ),
    storage_surface='sqlite_materialized_projection',
    repair_strategy='explicit_read_model_repair',
    query_surface='http_query_projection',
)


def projection_boundary_catalog() -> dict[str, dict[str, Any]]:
    """Return both authoritative projection-boundary descriptors."""
    return {
        'runtime': RUNTIME_PROJECTION_BOUNDARY.to_dict(),
        'query': QUERY_PROJECTION_BOUNDARY.to_dict(),
    }
