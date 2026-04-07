from __future__ import annotations

"""Focused application services for the gateway façade.

The public ``GatewayAppFacade`` intentionally stays stable for existing callers,
while these components hold narrower responsibilities:

- recipe management and projection refresh
- result/read-model queries
- station command orchestration and state mutation
- lightweight diagnostic actions
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import uuid

from inspection_interfaces.srv import ResetFault, StartInspection

from .recipe_store import RecipeActivationError
from .runtime_components import ServiceCallResult, utc_now


@dataclass(slots=True)
class GatewayRecipeService:
    """Manage recipe CRUD, activation, and projection into gateway state."""

    state: Any
    recipe_store: Any

    def refresh_recipes(self) -> list[dict[str, Any]]:
        """Refresh recipe metadata projected into gateway state."""
        default_recipe = self.recipe_store.current_default()
        active_recipe_id = str(default_recipe.get('recipe_id', '')) if isinstance(default_recipe, dict) else ''
        profiles = [self.recipe_store.to_hmi_profile(recipe, active_recipe_id=active_recipe_id) for recipe in self.recipe_store.load_all()]
        if not profiles and active_recipe_id:
            profiles = [self.recipe_store.to_hmi_profile(default_recipe, active_recipe_id=active_recipe_id)]
        active = next((item for item in profiles if item.get('enabled')), profiles[0] if profiles else None)
        activation = self.recipe_store.current_activation()
        self.state.active_recipe_id = str(active.get('id', active_recipe_id or '')) if active else active_recipe_id
        self.state.active_recipe_name = str(active.get('name', self.state.active_recipe_id or '--')) if active else '--'
        self.state.active_recipe_version = str(activation.get('recipeVersion', active.get('version', '') if active else ''))
        self.state.active_recipe_generation = str(activation.get('configGeneration', ''))
        self.state.recipe_activation_state = str(activation.get('activationState', ''))
        return profiles

    def recipe_history(self, recipe_id: str) -> dict[str, Any]:
        """Return recipe activation and revision history."""
        return {
            'activations': self.recipe_store.list_activation_history(recipe_id=recipe_id),
            'revisions': self.recipe_store.list_revision_history(recipe_id=recipe_id),
        }

    def save_recipe(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Persist a recipe from HMI payload and return its refreshed HMI profile."""
        recipe = self.recipe_store.save_from_hmi(payload)
        profiles = self.refresh_recipes()
        target = next((item for item in profiles if item['id'] == str(recipe.get('recipe_id', ''))), None)
        if target is None:
            raise RuntimeError('配方保存后无法重新装载。')
        return target

    def activate_recipe(self, recipe_id: str, *, operator: str) -> dict[str, Any]:
        """Activate a recipe for the next station start and refresh gateway state."""
        receipt = self.recipe_store.activate(recipe_id, operator=operator)
        self.refresh_recipes()
        self.state.recipe_activation_state = str(receipt.get('activationState', ''))
        self.state.last_updated_at = utc_now()
        self.state.guidance = '配方已切换，将在下一次启动任务时生效。'
        return receipt


@dataclass(slots=True)
class GatewayResultQueryService:
    """Expose read-model and artifact queries behind a narrow API."""

    result_store: Any
    artifact_url_resolver: Any

    def query_results(self, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        return self.result_store.query_result_page(**filters)

    def result_detail(self, result_id: str) -> dict[str, Any] | None:
        return self.result_store.get_result(result_id)

    def read_model_status(self) -> dict[str, Any]:
        return self.result_store.read_model_status()

    def batch_summary(self, *, batch_id: str) -> dict[str, Any]:
        return self.result_store.batch_summary(batch_id=batch_id)

    def artifact_url(self, path: str) -> str:
        return self.artifact_url_resolver(path)


@dataclass(slots=True)
class GatewayStationCommandService:
    """Own station command orchestration and state mutation.

    Args:
        state: Mutable gateway state object shared with the façade.
        event_bus: Gateway event bus used for public projections.
        recipe_store: Recipe persistence/activation facade.
        ros_bridge_getter: Callable returning the bound ROS bridge or ``None``.
        state_snapshot: Callable returning the current station snapshot payload.
        stats_snapshot: Callable returning the current count payload.
        capture_request: Callable that forwards a capture request into the ROS bridge.
        control_publisher: Callable that publishes a normalized control action.

    Boundary behavior:
        All methods fail closed when the ROS bridge is unavailable. Runtime
        acknowledgement of recipe activations is intentionally best-effort and
        never raises back into result projection.
    """

    state: Any
    event_bus: Any
    recipe_store: Any
    ros_bridge_getter: Any
    state_snapshot: Any
    stats_snapshot: Any
    capture_request: Any
    control_publisher: Any

    def call_start(self) -> tuple[bool, str]:
        ros_bridge = self.ros_bridge_getter()
        if ros_bridge is None:
            return False, 'ROS bridge unavailable.'
        request = StartInspection.Request()
        request.recipe_id = self.state.active_recipe_id or 'default_recipe'
        request.batch_id = self.state.pending_batch_id or self.state.batch_id or 'BATCH_DEMO'
        try:
            preflight = self.recipe_store.preflight_start_request(recipe_id=request.recipe_id, batch_id=request.batch_id)
            self.state.active_recipe_version = str(preflight.get('recipeVersion', self.state.active_recipe_version))
            self.state.active_recipe_generation = str(preflight.get('configGeneration', self.state.active_recipe_generation))
        except (RecipeActivationError, FileNotFoundError) as exc:
            activation = self.recipe_store.mark_activation_start_blocked(recipe_id=request.recipe_id, batch_id=request.batch_id, reason=str(exc))
            if activation:
                self.state.recipe_activation_state = str(activation.get('activationState', self.state.recipe_activation_state))
                self.state.active_recipe_version = str(activation.get('recipeVersion', self.state.active_recipe_version))
                self.state.active_recipe_generation = str(activation.get('configGeneration', self.state.active_recipe_generation))
            self.state.guidance = f'启动前配方校验失败：{exc}'
            self.state.last_updated_at = utc_now()
            self.event_bus.broadcast('station.state.updated', self.state_snapshot())
            return False, f'启动前配方校验失败：{exc}'
        result = ros_bridge.call_start(
            request,
            unavailable_message='未找到 /inspection/start 服务。',
            timeout_message='启动请求超时。',
        )
        if result.ok:
            self.state.batch_id = request.batch_id
            self.state.pending_batch_id = request.batch_id
            activation = self.recipe_store.mark_activation_start_requested(recipe_id=request.recipe_id, batch_id=request.batch_id)
            self.state.active_recipe_version = str(activation.get('recipeVersion', self.state.active_recipe_version))
            self.state.active_recipe_generation = str(activation.get('configGeneration', self.state.active_recipe_generation))
            self.state.recipe_activation_state = str(activation.get('activationState', self.state.recipe_activation_state))
            self.state.guidance = '启动请求已下发，等待运行链确认当前激活配方。'
            self.state.last_updated_at = utc_now()
            self.event_bus.broadcast('station.state.updated', self.state_snapshot())
        else:
            self.state.guidance = str(result.message or '启动失败。')
            self.state.last_updated_at = utc_now()
            self.event_bus.broadcast('station.state.updated', self.state_snapshot())
        return self._handle_service_result(result)

    def publish_control(self, action: str) -> None:
        if self.ros_bridge_getter() is None:
            raise RuntimeError('ROS bridge unavailable.')
        self.control_publisher(action)

    def request_capture(self, payload: dict[str, Any]) -> bool:
        return bool(self.capture_request(payload))

    def on_runtime_result_observed(self, payload: dict[str, Any]) -> None:
        recipe_id = str(payload.get('recipeId', '')).strip()
        if not recipe_id or recipe_id != str(self.state.active_recipe_id or '').strip():
            return
        activation = self.recipe_store.mark_runtime_acknowledged(
            recipe_id=recipe_id,
            observed_at=str(payload.get('timestamp', '')),
            batch_id=str(payload.get('batchId', '')),
            recipe_version=str(payload.get('recipeVersion', '')),
        )
        if not activation:
            return
        self.state.recipe_activation_state = str(activation.get('activationState', self.state.recipe_activation_state))
        self.state.active_recipe_version = str(activation.get('recipeVersion', self.state.active_recipe_version))
        self.state.active_recipe_generation = str(activation.get('configGeneration', self.state.active_recipe_generation))
        self.state.guidance = '运行链已确认当前激活配方。'
        self.state.last_updated_at = str(activation.get('runtimeAcknowledgedAt', utc_now()))
        self.event_bus.broadcast('station.state.updated', self.state_snapshot())

    def reset_fault(self) -> tuple[bool, str]:
        ros_bridge = self.ros_bridge_getter()
        if ros_bridge is None:
            return False, 'ROS bridge unavailable.'
        request = ResetFault.Request()
        request.operator_name = 'hmi_operator'
        request.comment = 'reset_from_hmi_gateway'
        result = ros_bridge.call_reset_fault(
            request,
            unavailable_message='未找到 /inspection/reset_fault 服务。',
            timeout_message='故障复位请求超时。',
        )
        if not result.ok and result.message == '未找到 /inspection/reset_fault 服务。':
            self.publish_control('reset')
            self.state.guidance = '复位服务不可用，已退回控制话题复位。'
            self.state.last_updated_at = utc_now()
            self.event_bus.broadcast('station.state.updated', self.state_snapshot())
            return True, '已退回控制话题复位。'
        if result.ok:
            fault = self.state.latest_fault
            if fault:
                self.event_bus.broadcast('fault.cleared', {'id': str(fault.get('id', 'last_fault'))})
                self.state.latest_fault = None
            self.state.guidance = '故障复位请求已完成。'
        else:
            self.state.guidance = str(result.message or '故障复位失败。')
        self.state.last_updated_at = utc_now()
        self.event_bus.broadcast('station.state.updated', self.state_snapshot())
        return self._handle_service_result(result)

    def new_batch(self) -> str:
        batch_id = datetime.now(UTC).strftime('BATCH-%Y%m%d-%H%M%S')
        self.state.pending_batch_id = batch_id
        self.state.batch_id = batch_id
        self.state.batch_baseline = {
            'total': self.state.absolute_stats['total'],
            'ok': self.state.absolute_stats['ok'],
            'ng': self.state.absolute_stats['ng'],
            'recheck': self.state.absolute_stats['recheck'],
        }
        self.state.continuous_run_count = 0
        self.state.last_updated_at = utc_now()
        self.state.guidance = f'新批次已创建：{batch_id}'
        self.event_bus.broadcast('station.state.updated', self.state_snapshot())
        self.event_bus.broadcast('station.count.updated', self.stats_snapshot())
        return batch_id

    def snapshot(self) -> dict[str, Any]:
        return {
            'activeRecipeId': str(self.state.active_recipe_id),
            'activeRecipeName': str(self.state.active_recipe_name),
            'batchId': str(self.state.batch_id),
            'phase': str(self.state.phase),
            'mode': str(self.state.mode),
        }

    def _handle_service_result(self, result: ServiceCallResult) -> tuple[bool, str]:
        return result.ok, result.message


@dataclass(slots=True)
class GatewayDiagnosticActionService:
    """Execute lightweight built-in diagnostic actions."""

    state: Any
    request_capture: Any
    control_publisher: Any

    def run(self, action: str) -> dict[str, Any]:
        action = str(action).upper()
        success = True
        message = '动作已执行。'
        if action == 'CAPTURE_FRAME':
            payload = {'trace_id': f'DIAG-{uuid.uuid4().hex[:8]}', 'item_id': -1, 'batch_id': self.state.batch_id}
            self.request_capture(payload)
            message = '已下发抓图请求。'
        elif action == 'TEST_SORT_ACTUATOR':
            self.control_publisher('manual_step_sort')
            message = '已下发分拣执行测试命令。'
        elif action == 'TEST_LIGHTING':
            self.control_publisher('manual_step_capture')
            message = '已触发照明/采图联动测试。'
        else:
            success = False
            message = f'不支持的诊断动作：{action}'
        return {
            'action': action,
            'success': success,
            'message': message,
            'executedAt': utc_now(),
            'frame': dict(self.state.latest_frame),
            'updatedItems': list(self.state.diagnostics),
        }
