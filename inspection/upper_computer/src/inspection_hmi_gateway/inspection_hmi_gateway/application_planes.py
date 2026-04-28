from __future__ import annotations

import os

"""Gateway application-plane composition.

This module is the authoritative composition root for the gateway business
boundary. It keeps control, query, projection, and recipe-management services
split into explicit planes so the runtime composition root never collapses back
into one wide service hub inline.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inspection_utils.io_common import resolve_runtime_path

from .app_components import (
    GatewayDiagnosticActionService,
    GatewayRecipeService,
    GatewayResultQueryService,
    GatewayStationCommandService,
)
from .recipe_store import RecipeStore
from .result_store import ResultStore
from .runtime_projection import GatewayReadModelProjector
from .state_store import GatewayState, GatewayStateStore


@dataclass(slots=True)
class GatewayRecipePlane:
    """Recipe CRUD and activation plane."""

    service: GatewayRecipeService


@dataclass(slots=True)
class GatewayControlPlane:
    """Mutating control plane for station and diagnostics actions."""

    station: GatewayStationCommandService
    diagnostics: GatewayDiagnosticActionService
    ros_bridge: Any | None = None

    def bind_ros_bridge(self, ros_bridge: Any) -> None:
        self.ros_bridge = ros_bridge


@dataclass(slots=True)
class GatewayQueryPlane:
    """Read/query plane for result, batch, and read-model access."""

    results: GatewayResultQueryService


@dataclass(slots=True)
class GatewayProjectionPlane:
    """Projection plane bridging runtime ROS events into gateway read models."""

    projector: GatewayReadModelProjector


@dataclass(slots=True)
class GatewayApplicationBoundary:
    """All authoritative gateway planes plus shared stateful stores."""

    state_store: GatewayStateStore
    recipe_store: RecipeStore
    result_store: ResultStore
    recipe_plane: GatewayRecipePlane
    control_plane: GatewayControlPlane
    query_plane: GatewayQueryPlane
    projection_plane: GatewayProjectionPlane

    @property
    def state(self) -> Any:
        return self.state_store.view

    @property
    def projector(self) -> GatewayReadModelProjector:
        return self.projection_plane.projector


def build_gateway_application_boundary(*, event_bus: Any, log_root: str | Path = 'logs/runtime', recipe_root: str | Path = 'config/recipes') -> GatewayApplicationBoundary:
    """Build the split gateway business boundary.

    Args:
        event_bus: Websocket/event fan-out hub used by control and projection planes.
        log_root: Result/read-model storage root.
        recipe_root: Recipe configuration storage root.

    Returns:
        Fully wired application boundary with explicit control/query/projection planes.

    Raises:
        Any exception propagated from store or service construction.

    Boundary behavior:
        The returned object preserves shared state and stores so transport
        runtimes and query services can coordinate through one boundary object
        while new code depends on the narrower plane objects directly.
    """
    resolved_log_root = resolve_runtime_path(log_root, start=__file__)
    resolved_recipe_root = resolve_runtime_path(recipe_root, start=__file__)
    state_store = GatewayStateStore(GatewayState())
    recipe_store = RecipeStore(resolved_recipe_root)
    result_store = ResultStore(resolved_log_root)
    state = state_store.view
    control_plane: GatewayControlPlane

    def _current_ros_bridge() -> Any:
        return control_plane.ros_bridge

    def _publish_control(action: str) -> None:
        bridge = _current_ros_bridge()
        if bridge is None:
            raise RuntimeError('ROS bridge unavailable.')
        bridge.publish_control(action)

    def _publish_capture(payload: dict[str, Any]) -> bool:
        bridge = _current_ros_bridge()
        return bool(bridge and bridge.publish_capture_request(payload))

    recipe_service = GatewayRecipeService(state=state, state_store=state_store, recipe_store=recipe_store)
    station_service = GatewayStationCommandService(
        state=state,
        state_store=state_store,
        event_bus=event_bus,
        recipe_store=recipe_store,
        ros_bridge_getter=_current_ros_bridge,
        state_snapshot=state_store.snapshot_payload,
        stats_snapshot=state_store.stats_payload,
        capture_request=_publish_capture,
        control_publisher=_publish_control,
    )
    control_plane = GatewayControlPlane(
        station=station_service,
        diagnostics=GatewayDiagnosticActionService(
            state=state,
            state_store=state_store,
            request_capture=station_service.request_capture,
            control_publisher=_publish_control,
        ),
        ros_bridge=None,
    )
    emit_created_alias = str(os.environ.get('INSPECTION_RESULT_CREATED_ALIAS_ENABLED', '0')).strip().lower() in {'1', 'true', 'yes', 'on'}
    projector = GatewayReadModelProjector(
        state=state,
        state_store=state_store,
        event_bus=event_bus,
        log_root=resolved_log_root,
        on_runtime_result_observed=station_service.on_runtime_result_observed,
        emit_created_alias=emit_created_alias,
    )
    query_service = GatewayResultQueryService(result_store=result_store, artifact_url_resolver=projector.artifact_url)
    return GatewayApplicationBoundary(
        state_store=state_store,
        recipe_store=recipe_store,
        result_store=result_store,
        recipe_plane=GatewayRecipePlane(service=recipe_service),
        control_plane=control_plane,
        query_plane=GatewayQueryPlane(results=query_service),
        projection_plane=GatewayProjectionPlane(projector=projector),
    )
