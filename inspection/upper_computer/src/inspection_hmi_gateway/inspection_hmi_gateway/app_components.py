from __future__ import annotations

"""Focused application services for the gateway runtime boundary.

These components hold narrower responsibilities behind the authoritative
``GatewayApplicationService`` runtime entrypoint:

- recipe management and projection refresh
- result/read-model queries
- station command orchestration and state mutation
- lightweight diagnostic actions
"""

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import os
from typing import Any, Callable
import uuid

try:
    from inspection_interfaces.srv import ResetFault, StartInspection
except ImportError:  # pragma: no cover - unit-test fallback without generated ROS services
    class StartInspection:  # type: ignore[override]
        class Request:
            def __init__(self) -> None:
                self.recipe_id = ''
                self.batch_id = ''

    class ResetFault:  # type: ignore[override]
        class Request:
            def __init__(self) -> None:
                self.operator_name = ''
                self.comment = ''

from .recipe_store import RecipeActivationError
from .runtime_components import ServiceCallResult, utc_now


def reset_topic_fallback_enabled() -> bool:
    """Return whether control-topic reset fallback is explicitly enabled.

    The reset service path is authoritative. Topic fallback is disabled by
    default and may only be re-enabled through an explicit rollback/migration
    environment override.
    """
    return str(os.environ.get('INSPECTION_RESET_TOPIC_FALLBACK_ENABLED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}


@dataclass(slots=True)
class GatewayRecipeService:
    """Manage recipe CRUD, activation, and projection into gateway state."""

    state: Any
    recipe_store: Any
    state_store: Any | None = None

    def _mutate_state(self, mutator: Callable[[Any], Any]) -> Any:
        if self.state_store is not None:
            return self.state_store.mutate(mutator)
        mutator(self.state)
        return deepcopy(self.state)

    def refresh_recipes(self) -> list[dict[str, Any]]:
        """Refresh recipe metadata projected into gateway state."""
        default_recipe = self.recipe_store.current_default()
        active_recipe_id = str(default_recipe.get('recipe_id', '')) if isinstance(default_recipe, dict) else ''
        profiles = [self.recipe_store.to_hmi_profile(recipe, active_recipe_id=active_recipe_id) for recipe in self.recipe_store.load_all()]
        if not profiles and active_recipe_id:
            profiles = [self.recipe_store.to_hmi_profile(default_recipe, active_recipe_id=active_recipe_id)]
        active = next((item for item in profiles if item.get('enabled')), profiles[0] if profiles else None)
        activation = self.recipe_store.current_activation()

        def _apply(state: Any) -> None:
            state.active_recipe_id = str(active.get('id', active_recipe_id or '')) if active else active_recipe_id
            state.active_recipe_name = str(active.get('name', state.active_recipe_id or '--')) if active else '--'
            state.active_recipe_version = str(activation.get('recipeVersion', active.get('version', '') if active else ''))
            state.active_recipe_generation = str(activation.get('configGeneration', ''))
            state.recipe_activation_state = str(activation.get('activationState', ''))

        self._mutate_state(_apply)
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

        def _apply(state: Any) -> None:
            state.recipe_activation_state = str(receipt.get('activationState', ''))
            state.last_updated_at = utc_now()
            state.guidance = '配方已切换，将在下一次启动任务时生效。'

        self._mutate_state(_apply)
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

    def repair_read_model(self) -> dict[str, Any]:
        """Trigger an explicit read-model repair and return the new status.

        Args:
            None.

        Returns:
            The refreshed read-model status payload after repair completes.

        Raises:
            Exception: Any rebuild/refresh error propagated by the repository.

        Boundary behavior:
            The repair is synchronous on the current gateway process. Callers
            should treat it as a maintenance operation instead of relying on
            query-side implicit refresh.
        """
        self.result_store.repair_read_model()
        return self.result_store.read_model_status(refresh=False)

    def batch_summary(self, *, batch_id: str) -> dict[str, Any]:
        return self.result_store.batch_summary(batch_id=batch_id)

    def result_statistics(self, **filters: Any) -> dict[str, Any]:
        return self.result_store.query_statistics(**filters)

    def artifact_url(self, path: str) -> str:
        return self.artifact_url_resolver(path)


@dataclass(slots=True)
class GatewayStationCommandService:
    """Own station command orchestration and state mutation.

    Args:
        state: Mutable or proxy gateway state object shared with the façade.
        state_store: Optional transactional state store used to apply atomic
            multi-field mutations.
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
    state_store: Any | None = None

    def _mutate_state(self, mutator: Callable[[Any], Any]) -> Any:
        if self.state_store is not None:
            return self.state_store.mutate(mutator)
        mutator(self.state)
        return deepcopy(self.state)

    def _read_state(self, reader: Callable[[Any], Any]) -> Any:
        if self.state_store is not None:
            return self.state_store.read(reader)
        return reader(self.state)

    def call_start(self, *, recipe_id: str | None = None, batch_id: str | None = None) -> tuple[bool, str]:
        """Start the inspection runtime with optional recipe/batch overrides.

        Args:
            recipe_id: Optional recipe identifier overriding the currently active
                recipe stored in the gateway snapshot.
            batch_id: Optional batch identifier overriding the pending batch id.

        Returns:
            ``(ok, message)`` reflecting the downstream ROS service result.

        Raises:
            No exception is raised; failures are returned in-band and projected
            back into gateway state.

        Boundary behavior:
            When override values are provided they become the authoritative
            preflight/start context for this request and are written back into
            the gateway state before the ROS service call is issued.
        """
        ros_bridge = self.ros_bridge_getter()
        if ros_bridge is None:
            return False, 'ROS bridge unavailable.'
        request = StartInspection.Request()
        explicit_recipe_override = str(recipe_id or '').strip()
        normalized_recipe_id = explicit_recipe_override or self._read_state(lambda state: state.active_recipe_id or 'default_recipe')
        normalized_batch_id = str(batch_id or '').strip() or self._read_state(lambda state: state.pending_batch_id or state.batch_id or 'BATCH_DEMO')
        request.recipe_id = normalized_recipe_id
        request.batch_id = normalized_batch_id

        def _apply_requested_start_context(state: Any) -> None:
            state.active_recipe_id = normalized_recipe_id
            state.pending_batch_id = normalized_batch_id

        self._mutate_state(_apply_requested_start_context)
        try:
            if explicit_recipe_override:
                current_activation_recipe_id = str(self.recipe_store.current_activation().get('recipeId', '')).strip()
                if current_activation_recipe_id != request.recipe_id:
                    activation_override = self.recipe_store.activate(request.recipe_id, operator='gateway_start_override')

                    def _apply_override_activation(state: Any) -> None:
                        state.active_recipe_id = request.recipe_id
                        state.active_recipe_version = str(activation_override.get('recipeVersion', state.active_recipe_version))
                        state.active_recipe_generation = str(activation_override.get('configGeneration', state.active_recipe_generation))
                        state.recipe_activation_state = str(activation_override.get('activationState', state.recipe_activation_state))

                    self._mutate_state(_apply_override_activation)
            preflight = self.recipe_store.preflight_start_request(recipe_id=request.recipe_id, batch_id=request.batch_id)

            def _apply_preflight(state: Any) -> None:
                state.active_recipe_id = request.recipe_id
                state.active_recipe_version = str(preflight.get('recipeVersion', state.active_recipe_version))
                state.active_recipe_generation = str(preflight.get('configGeneration', state.active_recipe_generation))

            self._mutate_state(_apply_preflight)
        except (RecipeActivationError, FileNotFoundError) as exc:
            activation = self.recipe_store.mark_activation_start_blocked(recipe_id=request.recipe_id, batch_id=request.batch_id, reason=str(exc))

            def _apply_failed_preflight(state: Any) -> None:
                if activation:
                    state.recipe_activation_state = str(activation.get('activationState', state.recipe_activation_state))
                    state.active_recipe_version = str(activation.get('recipeVersion', state.active_recipe_version))
                    state.active_recipe_generation = str(activation.get('configGeneration', state.active_recipe_generation))
                state.guidance = f'启动前配方校验失败：{exc}'
                state.last_updated_at = utc_now()

            self._mutate_state(_apply_failed_preflight)
            self.event_bus.broadcast('station.state.updated', self.state_snapshot())
            return False, f'启动前配方校验失败：{exc}'
        result = ros_bridge.call_start(
            request,
            unavailable_message='未找到 /inspection/start 服务。',
            timeout_message='启动请求超时。',
        )
        if result.ok:
            activation = self.recipe_store.mark_activation_start_requested(recipe_id=request.recipe_id, batch_id=request.batch_id)

            def _apply_start_success(state: Any) -> None:
                state.active_recipe_id = request.recipe_id
                state.batch_id = request.batch_id
                state.pending_batch_id = request.batch_id
                state.active_recipe_version = str(activation.get('recipeVersion', state.active_recipe_version))
                state.active_recipe_generation = str(activation.get('configGeneration', state.active_recipe_generation))
                state.recipe_activation_state = str(activation.get('activationState', state.recipe_activation_state))
                state.guidance = '启动请求已下发，等待运行链确认当前激活配方。'
                state.last_updated_at = utc_now()

            self._mutate_state(_apply_start_success)
            self.event_bus.broadcast('station.state.updated', self.state_snapshot())
        else:
            def _apply_start_failure(state: Any) -> None:
                state.guidance = str(result.message or '启动失败。')
                state.last_updated_at = utc_now()

            self._mutate_state(_apply_start_failure)
            self.event_bus.broadcast('station.state.updated', self.state_snapshot())
        return self._handle_service_result(result)

    def request_maintenance_mode(self, enabled: bool, *, actor: str = 'anonymous') -> dict[str, Any]:
        """Request a real maintenance-mode transition through the supervisor plane.

        Args:
            enabled: Target maintenance-mode state requested by the caller.
            actor: Audit-friendly actor label used in guidance text.

        Returns:
            Station snapshot payload after the request is projected locally.

        Raises:
            RuntimeError: When the ROS bridge is unavailable or the command
                envelope cannot be published.

        Boundary behavior:
            The method updates only the requested-transition fields locally.
            ``maintenance.enabled`` and ``supervisorMode`` remain driven by
            supervisor/FSM runtime events so the gateway does not overstate the
            committed control-plane state.
        """
        ros_bridge = self.ros_bridge_getter()
        if ros_bridge is None:
            raise RuntimeError('ROS bridge unavailable.')
        target_mode = 'MAINTENANCE' if enabled else 'PAUSED'
        reason = f'gateway_maintenance_request:{actor}' if enabled else f'gateway_resume_request:{actor}'
        if not bool(getattr(ros_bridge, 'publish_supervisor_command', None) and ros_bridge.publish_supervisor_command('set_mode', mode=target_mode, reason=reason)):
            raise RuntimeError('failed_to_publish_supervisor_command')

        def _apply(state: Any) -> None:
            state.maintenance_requested = bool(enabled)
            state.maintenance_transition_state = 'ENTERING' if enabled else 'EXITING'
            if enabled:
                state.guidance = f'已请求进入维护模式，等待控制链确认。操作人：{actor}'
            else:
                state.guidance = f'已请求退出维护模式，等待控制链确认。操作人：{actor}'
            state.last_updated_at = utc_now()

        self._mutate_state(_apply)
        snapshot = self.state_snapshot()
        self.event_bus.broadcast('station.state.updated', snapshot)
        return snapshot

    def publish_control(self, action: str) -> None:
        if self.ros_bridge_getter() is None:
            raise RuntimeError('ROS bridge unavailable.')
        self.control_publisher(action)

    def request_capture(self, payload: dict[str, Any]) -> bool:
        return bool(self.capture_request(payload))

    def on_runtime_result_observed(self, payload: dict[str, Any]) -> None:
        recipe_id = str(payload.get('recipeId', '')).strip()
        active_recipe_id = self._read_state(lambda state: str(state.active_recipe_id or '').strip())
        if not recipe_id or recipe_id != active_recipe_id:
            return
        activation = self.recipe_store.mark_runtime_acknowledged(
            recipe_id=recipe_id,
            observed_at=str(payload.get('timestamp', '')),
            batch_id=str(payload.get('batchId', '')),
            recipe_version=str(payload.get('recipeVersion', '')),
        )
        if not activation:
            return

        def _apply_runtime_ack(state: Any) -> None:
            state.recipe_activation_state = str(activation.get('activationState', state.recipe_activation_state))
            state.active_recipe_version = str(activation.get('recipeVersion', state.active_recipe_version))
            state.active_recipe_generation = str(activation.get('configGeneration', state.active_recipe_generation))
            state.guidance = '运行链已确认当前激活配方。'
            state.last_updated_at = str(activation.get('runtimeAcknowledgedAt', utc_now()))

        self._mutate_state(_apply_runtime_ack)
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
            if not reset_topic_fallback_enabled():
                def _apply_fallback_blocked(state: Any) -> None:
                    state.guidance = '复位服务不可用，且未启用控制话题复位回退。'
                    state.last_updated_at = utc_now()

                self._mutate_state(_apply_fallback_blocked)
                self.event_bus.broadcast('station.state.updated', self.state_snapshot())
                return False, '未找到 /inspection/reset_fault 服务，且未启用控制话题复位回退。'
            self.publish_control('reset')

            def _apply_fallback_reset(state: Any) -> None:
                state.guidance = '复位服务不可用，已通过控制话题执行回退复位。'
                state.last_updated_at = utc_now()

            self._mutate_state(_apply_fallback_reset)
            self.event_bus.broadcast('station.state.updated', self.state_snapshot())
            return True, '已通过控制话题执行回退复位。'
        if result.ok:
            fault = self._read_state(lambda state: deepcopy(state.latest_fault))

            def _apply_reset_success(state: Any) -> None:
                state.latest_fault = None
                state.guidance = '故障复位请求已完成。'
                state.last_updated_at = utc_now()

            if fault:
                self.event_bus.broadcast('fault.cleared', {'id': str(fault.get('id', 'last_fault'))})
            self._mutate_state(_apply_reset_success)
        else:
            def _apply_reset_failure(state: Any) -> None:
                state.guidance = str(result.message or '故障复位失败。')
                state.last_updated_at = utc_now()

            self._mutate_state(_apply_reset_failure)
        self.event_bus.broadcast('station.state.updated', self.state_snapshot())
        return self._handle_service_result(result)

    def new_batch(self) -> str:
        batch_id = datetime.now(UTC).strftime('BATCH-%Y%m%d-%H%M%S')

        def _apply_new_batch(state: Any) -> None:
            state.pending_batch_id = batch_id
            state.batch_id = batch_id
            state.batch_baseline = {
                'total': state.absolute_stats['total'],
                'ok': state.absolute_stats['ok'],
                'ng': state.absolute_stats['ng'],
                'recheck': state.absolute_stats['recheck'],
            }
            state.continuous_run_count = 0
            state.last_updated_at = utc_now()
            state.guidance = f'新批次已创建：{batch_id}'

        self._mutate_state(_apply_new_batch)
        self.event_bus.broadcast('station.state.updated', self.state_snapshot())
        self.event_bus.broadcast('station.count.updated', self.stats_snapshot())
        return batch_id

    def snapshot(self) -> dict[str, Any]:
        return self._read_state(
            lambda state: {
                'activeRecipeId': str(state.active_recipe_id),
                'activeRecipeName': str(state.active_recipe_name),
                'batchId': str(state.batch_id),
                'phase': str(state.phase),
                'mode': str(state.mode),
                'stateVersion': int(getattr(self.state_store, 'version', 0)),
            }
        )

    def _handle_service_result(self, result: ServiceCallResult) -> tuple[bool, str]:
        return result.ok, result.message


@dataclass(slots=True)
class GatewayDiagnosticActionService:
    """Execute lightweight built-in diagnostic actions."""

    state: Any
    request_capture: Any
    control_publisher: Any
    state_store: Any | None = None

    def _read_state(self, reader: Callable[[Any], Any]) -> Any:
        if self.state_store is not None:
            return self.state_store.read(reader)
        return reader(self.state)

    def run(self, action: str) -> dict[str, Any]:
        """Execute a diagnostics action guarded by the real maintenance state.

        Args:
            action: Public diagnostics action name from the HMI API.

        Returns:
            Result payload surfaced back to HTTP callers.

        Raises:
            RuntimeError: When the requested action requires maintenance mode but
                the runtime has not yet entered manual/maintenance state.

        Boundary behavior:
            The method checks the gateway read-model projection instead of any UI
            local flag so exposed diagnostics actions cannot bypass the control
            plane.
        """
        action = str(action).upper()
        maintenance_active = bool(self._read_state(lambda state: bool(getattr(state, 'maintenance_active', False))))
        transition_state = str(self._read_state(lambda state: getattr(state, 'maintenance_transition_state', 'LOCKED'))).upper()
        if not maintenance_active:
            if transition_state == 'ENTERING':
                raise RuntimeError('维护模式请求已下发，但系统尚未确认进入手动模式。')
            raise RuntimeError('维护模式未生效，危险动作已锁定。')
        success = True
        message = '动作已执行。'
        batch_id = self._read_state(lambda state: str(state.batch_id))
        if action == 'CAPTURE_FRAME':
            payload = {'trace_id': f'DIAG-{uuid.uuid4().hex[:8]}', 'item_id': -1, 'batch_id': batch_id}
            if not bool(self.request_capture(payload)):
                raise RuntimeError('抓图请求下发失败。')
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
            'frame': self._read_state(lambda state: dict(state.latest_frame)),
            'updatedItems': self._read_state(lambda state: list(state.diagnostics)),
        }
