from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from inspection_utils.paths import resolve_runtime_path

from .app_components import (
    GatewayDiagnosticActionService,
    GatewayRecipeService,
    GatewayResultQueryService,
    GatewayStationCommandService,
)
from .recipe_store import RecipeStore
from .result_store import ResultStore
from .runtime_components import GatewayReadModelProjector, utc_now


@dataclass
class GatewayState:
    """Mutable gateway read model projected to HTTP and websocket clients."""

    phase: str = 'BOOT'
    mode: str = 'IDLE'
    batch_id: str = 'BATCH_DEMO'
    active_recipe_id: str = ''
    active_recipe_name: str = '--'
    active_recipe_version: str = ''
    active_recipe_generation: str = ''
    recipe_activation_state: str = ''
    cycle_index: int = 0
    last_updated_at: str = field(default_factory=utc_now)
    guidance: str = '等待系统连接。'
    absolute_stats: dict[str, float] = field(default_factory=lambda: {'total': 0, 'ok': 0, 'ng': 0, 'recheck': 0, 'yieldRate': 0.0, 'avgCycleMs': 0.0})
    batch_baseline: dict[str, float] = field(default_factory=lambda: {'total': 0, 'ok': 0, 'ng': 0, 'recheck': 0})
    continuous_run_count: int = 0
    latest_frame: dict[str, Any] = field(default_factory=lambda: {'url': '', 'capturedAt': utc_now(), 'annotated': True})
    latest_fault: dict[str, Any] | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    pending_batch_id: str = 'BATCH_DEMO'
    heartbeats: dict[str, dict[str, Any]] = field(default_factory=dict)

    def snapshot_payload(self) -> dict[str, Any]:
        return {
            'phase': self.phase,
            'mode': self.mode,
            'batchId': self.batch_id,
            'activeRecipeId': self.active_recipe_id,
            'activeRecipeName': self.active_recipe_name,
            'activeRecipeVersion': self.active_recipe_version,
            'activeRecipeGeneration': self.active_recipe_generation,
            'recipeActivationState': self.recipe_activation_state,
            'cycleIndex': self.cycle_index,
            'lastUpdatedAt': self.last_updated_at,
            'guidance': self.guidance,
        }

    def stats_payload(self) -> dict[str, Any]:
        total = max(0.0, self.absolute_stats['total'] - self.batch_baseline['total'])
        ok = max(0.0, self.absolute_stats['ok'] - self.batch_baseline['ok'])
        ng = max(0.0, self.absolute_stats['ng'] - self.batch_baseline['ng'])
        recheck = max(0.0, self.absolute_stats['recheck'] - self.batch_baseline['recheck'])
        yield_rate = ok / total if total > 0 else 0.0
        return {
            'total': int(total),
            'ok': int(ok),
            'ng': int(ng),
            'recheck': int(recheck),
            'yieldRate': round(yield_rate, 4),
            'continuousRunCount': int(self.continuous_run_count),
            'avgCycleMs': round(float(self.absolute_stats['avgCycleMs']), 3),
        }


class GatewayAppFacade:
    """Compatibility façade around split gateway application services."""

    def __init__(self, *, event_bus: Any, log_root: str | Path = 'logs/runtime', recipe_root: str | Path = 'config/recipes') -> None:
        self.event_bus = event_bus
        self.log_root = resolve_runtime_path(log_root, start=__file__)
        self.recipe_root = resolve_runtime_path(recipe_root, start=__file__)
        self.state = GatewayState()
        self.recipe_store = RecipeStore(self.recipe_root)
        self.result_store = ResultStore(self.log_root)
        self.ros_bridge: Any | None = None
        self.recipe_service = GatewayRecipeService(state=self.state, recipe_store=self.recipe_store)
        self.station_service = GatewayStationCommandService(
            state=self.state,
            event_bus=self.event_bus,
            recipe_store=self.recipe_store,
            ros_bridge_getter=lambda: self.ros_bridge,
            state_snapshot=self.snapshot_payload,
            stats_snapshot=self.stats_payload,
            capture_request=lambda payload: bool(self.ros_bridge and self.ros_bridge.publish_capture_request(payload)),
            control_publisher=self._publish_control,
        )
        self.projector = GatewayReadModelProjector(
            state=self.state,
            event_bus=self.event_bus,
            log_root=self.log_root,
            on_runtime_result_observed=self.station_service.on_runtime_result_observed,
        )
        self.query_service = GatewayResultQueryService(result_store=self.result_store, artifact_url_resolver=self.projector.artifact_url)
        self.diagnostic_service = GatewayDiagnosticActionService(
            state=self.state,
            request_capture=self.station_service.request_capture,
            control_publisher=self._publish_control,
        )

    def bind_ros_bridge(self, ros_bridge: Any) -> None:
        """Attach the ROS transport bridge used for commands and services."""
        self.ros_bridge = ros_bridge

    def snapshot_payload(self) -> dict[str, Any]:
        return self.state.snapshot_payload()

    def stats_payload(self) -> dict[str, Any]:
        return self.state.stats_payload()

    def diagnostic_items(self) -> list[dict[str, Any]]:
        return list(self.state.diagnostics)

    def refresh_recipes(self) -> list[dict[str, Any]]:
        return self.recipe_service.refresh_recipes()

    def recipe_history(self, recipe_id: str) -> dict[str, Any]:
        return self.recipe_service.recipe_history(recipe_id)

    def save_recipe(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.recipe_service.save_recipe(payload)

    def activate_recipe(self, recipe_id: str, *, operator: str) -> dict[str, Any]:
        return self.recipe_service.activate_recipe(recipe_id, operator=operator)

    def query_results(self, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        return self.query_service.query_results(**filters)

    def result_detail(self, result_id: str) -> dict[str, Any] | None:
        return self.query_service.result_detail(result_id)

    def read_model_status(self) -> dict[str, Any]:
        return self.query_service.read_model_status()

    def batch_summary(self, *, batch_id: str) -> dict[str, Any]:
        return self.query_service.batch_summary(batch_id=batch_id)

    def artifact_url(self, path: str) -> str:
        return self.query_service.artifact_url(path)

    def call_start(self) -> tuple[bool, str]:
        return self.station_service.call_start()

    def publish_control(self, action: str) -> None:
        self.station_service.publish_control(action)

    def request_capture(self, payload: dict[str, Any]) -> bool:
        return self.station_service.request_capture(payload)

    def reset_fault(self) -> tuple[bool, str]:
        return self.station_service.reset_fault()

    def new_batch(self) -> str:
        return self.station_service.new_batch()

    def run_diagnostic_action(self, action: str) -> dict[str, Any]:
        return self.diagnostic_service.run(action)

    def snapshot(self) -> dict[str, Any]:
        return self.station_service.snapshot()

    def _publish_control(self, action: str) -> None:
        if self.ros_bridge is None:
            raise RuntimeError('ROS bridge unavailable.')
        self.ros_bridge.publish_control(action)
