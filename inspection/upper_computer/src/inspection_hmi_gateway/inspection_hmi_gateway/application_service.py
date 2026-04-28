from __future__ import annotations

"""Gateway runtime application service.

This module exposes the authoritative gateway business boundary as one cohesive
runtime service object. The object exists so transport runtimes, websocket
bootstrapping, and HTTP services share one stable composition root while the
underlying implementation remains split into explicit recipe/control/query/
projection planes.
"""

from pathlib import Path
from typing import Any

from .application_planes import GatewayApplicationBoundary, build_gateway_application_boundary


class GatewayApplicationService:
    """Expose the split gateway planes through one runtime service object.

    Args:
        event_bus: Gateway event bus used for websocket fan-out and runtime
            projection notifications.
        log_root: Runtime log root containing result artifacts and read-model
            storage.
        recipe_root: Recipe repository root.

    Returns:
        None. Callers use instance methods and plane attributes.

    Raises:
        Any exception raised by boundary construction propagates to the caller.

    Boundary behavior:
        The service owns the authoritative business boundary for the gateway
        process. Callers may coordinate through this object, but business logic
        must continue to live inside the explicit plane services instead of
        re-centralizing into one monolithic module.
    """

    def __init__(self, *, event_bus: Any, log_root: str | Path = 'logs/runtime', recipe_root: str | Path = 'config/recipes') -> None:
        self.event_bus = event_bus
        self.boundary: GatewayApplicationBoundary = build_gateway_application_boundary(
            event_bus=event_bus,
            log_root=log_root,
            recipe_root=recipe_root,
        )
        self.state_store = self.boundary.state_store
        self.state = self.boundary.state
        self.recipe_store = self.boundary.recipe_store
        self.result_store = self.boundary.result_store
        self.projector = self.boundary.projector
        self.recipe_plane = self.boundary.recipe_plane
        self.control_plane = self.boundary.control_plane
        self.query_plane = self.boundary.query_plane
        self.ros_bridge: Any | None = None

    def bind_ros_bridge(self, ros_bridge: Any) -> None:
        """Attach the ROS transport bridge used for commands and services."""
        self.ros_bridge = ros_bridge
        self.control_plane.bind_ros_bridge(ros_bridge)

    def snapshot_payload(self) -> dict[str, Any]:
        """Return the current projected station snapshot payload."""
        return self.state_store.snapshot_payload()

    def stats_payload(self) -> dict[str, Any]:
        """Return the current projected station counter payload."""
        return self.state_store.stats_payload()

    def diagnostic_items(self) -> list[dict[str, Any]]:
        """Return projected diagnostics items for the HMI query plane."""
        return self.state_store.diagnostics()

    def refresh_recipes(self) -> list[dict[str, Any]]:
        """Reload recipe metadata and project it into runtime state."""
        return self.recipe_plane.service.refresh_recipes()

    def recipe_history(self, recipe_id: str) -> dict[str, Any]:
        """Return recipe activation and revision history for ``recipe_id``."""
        return self.recipe_plane.service.recipe_history(recipe_id)

    def save_recipe(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist one recipe payload and return the refreshed HMI profile."""
        return self.recipe_plane.service.save_recipe(payload)

    def activate_recipe(self, recipe_id: str, *, operator: str) -> dict[str, Any]:
        """Activate one recipe for subsequent station starts."""
        return self.recipe_plane.service.activate_recipe(recipe_id, operator=operator)

    def query_results(self, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        """Query result records through the read-model query plane."""
        return self.query_plane.results.query_results(**filters)

    def result_detail(self, result_id: str) -> dict[str, Any] | None:
        """Return one projected result detail payload."""
        return self.query_plane.results.result_detail(result_id)

    def read_model_status(self) -> dict[str, Any]:
        """Return read-model synchronization status."""
        return self.query_plane.results.read_model_status()

    def repair_read_model(self) -> dict[str, Any]:
        """Execute an explicit read-model repair and return the refreshed status."""
        return self.query_plane.results.repair_read_model()

    def batch_summary(self, *, batch_id: str) -> dict[str, Any]:
        """Return the projected summary for one batch."""
        return self.query_plane.results.batch_summary(batch_id=batch_id)

    def result_statistics(self, **filters: Any) -> dict[str, Any]:
        """Return projected statistics for the supplied result filters."""
        return self.query_plane.results.result_statistics(**filters)

    def artifact_url(self, path: str) -> str:
        """Resolve one runtime artifact path into a gateway download URL."""
        return self.query_plane.results.artifact_url(path)

    def call_start(self, *, recipe_id: str | None = None, batch_id: str | None = None) -> tuple[bool, str]:
        """Submit one start request after recipe preflight and state projection."""
        return self.control_plane.station.call_start(recipe_id=recipe_id, batch_id=batch_id)

    def publish_control(self, action: str) -> None:
        """Publish one canonical control action into the ROS transport boundary."""
        self.control_plane.station.publish_control(action)

    def request_capture(self, payload: dict[str, Any]) -> bool:
        """Publish one capture request through the control plane."""
        return self.control_plane.station.request_capture(payload)

    def reset_fault(self) -> tuple[bool, str]:
        """Request a station fault reset through the control plane."""
        return self.control_plane.station.reset_fault()

    def new_batch(self) -> str:
        """Allocate and project a new batch identifier."""
        return self.control_plane.station.new_batch()

    def request_maintenance_mode(self, enabled: bool, *, actor: str = 'anonymous') -> dict[str, Any]:
        """Request a maintenance-mode transition through the control plane."""
        return self.control_plane.station.request_maintenance_mode(enabled, actor=actor)

    def run_diagnostic_action(self, action: str) -> dict[str, Any]:
        """Execute one diagnostics action through the maintenance-gated plane."""
        return self.control_plane.diagnostics.run(action)

    def snapshot(self) -> dict[str, Any]:
        """Return the minimal runtime snapshot exposed to health and telemetry code."""
        return self.control_plane.station.snapshot()
