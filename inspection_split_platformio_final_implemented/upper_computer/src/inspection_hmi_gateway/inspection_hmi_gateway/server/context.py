from __future__ import annotations

from contextvars import ContextVar
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..export_service import BatchExportService
from ..replay_service import ReplayService
from .auth import AuthService
from .persistence import MetadataRepository
from .responses import utc_now
from ..recipe_store import RecipeActivationError


_request_id: ContextVar[str] = ContextVar('inspection_gateway_request_id', default='')

LOGGER = logging.getLogger(__name__)


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()


class _LegacyNodeFacadeAdapter:
    """Adapt older gateway test doubles to the newer application-facade contract."""

    def __init__(self, node: Any) -> None:
        self._node = node
        self.state = getattr(node, 'state', None)
        self.recipe_store = getattr(node, 'recipe_store', None)
        self.result_store = getattr(node, 'result_store', None)

    def snapshot_payload(self) -> dict[str, Any]:
        state = getattr(self._node, 'state', None)
        return state.snapshot_payload() if state is not None and hasattr(state, 'snapshot_payload') else {}

    def stats_payload(self) -> dict[str, Any]:
        state = getattr(self._node, 'state', None)
        return state.stats_payload() if state is not None and hasattr(state, 'stats_payload') else {}

    def diagnostic_items(self) -> list[dict[str, Any]]:
        state = getattr(self._node, 'state', None)
        items = getattr(state, 'diagnostics', []) if state is not None else []
        return [item for item in items if isinstance(item, dict)]

    def refresh_recipes(self) -> list[dict[str, Any]]:
        return self._node.refresh_recipes()

    def recipe_history(self, recipe_id: str) -> dict[str, Any]:
        store = self.recipe_store
        return {
            'activations': store.list_activation_history(recipe_id=recipe_id),
            'revisions': store.list_revision_history(recipe_id=recipe_id),
        }

    def save_recipe(self, payload: dict[str, Any]) -> dict[str, Any]:
        recipe = self.recipe_store.save_from_hmi(payload)
        profiles = self.refresh_recipes()
        target = next((item for item in profiles if item['id'] == str(recipe.get('recipe_id', ''))), None)
        if target is None:
            raise RuntimeError('配方保存后无法重新装载。')
        return target

    def activate_recipe(self, recipe_id: str, *, operator: str) -> dict[str, Any]:
        receipt = self.recipe_store.activate(recipe_id, operator=operator)
        self.refresh_recipes()
        state = getattr(self._node, 'state', None)
        if state is not None:
            state.last_updated_at = utc_now()
            if hasattr(state, 'recipe_activation_state'):
                state.recipe_activation_state = str(receipt.get('activationState', ''))
            if hasattr(state, 'active_recipe_version'):
                state.active_recipe_version = str(receipt.get('recipeVersion', getattr(state, 'active_recipe_version', '')))
            if hasattr(state, 'active_recipe_generation'):
                state.active_recipe_generation = str(receipt.get('configGeneration', getattr(state, 'active_recipe_generation', '')))
            if hasattr(state, 'guidance'):
                state.guidance = '配方已切换，将在下一次启动任务时生效。'
        return receipt

    def query_results(self, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        return self.result_store.query_result_page(**filters)

    def result_detail(self, result_id: str) -> dict[str, Any] | None:
        return self.result_store.get_result(result_id)

    def batch_summary(self, *, batch_id: str) -> dict[str, Any]:
        return self.result_store.batch_summary(batch_id=batch_id)

    def artifact_url(self, path: str) -> str:
        if hasattr(self._node, '_artifact_url'):
            return self._node._artifact_url(path)
        normalized = str(path or '').replace('\\', '/').lstrip('/')
        return f'/artifacts/{normalized}' if normalized else ''

    def call_start(self) -> tuple[bool, str]:
        state = getattr(self._node, 'state', None)
        recipe_id = str(getattr(state, 'active_recipe_id', '') or '') if state is not None else ''
        batch_id = str(getattr(state, 'pending_batch_id', '') or getattr(state, 'batch_id', '') or '') if state is not None else ''
        if self.recipe_store is not None and recipe_id:
            try:
                preflight = self.recipe_store.preflight_start_request(recipe_id=recipe_id, batch_id=batch_id)
                if state is not None and hasattr(state, 'active_recipe_version'):
                    state.active_recipe_version = str(preflight.get('recipeVersion', getattr(state, 'active_recipe_version', '')))
                if state is not None and hasattr(state, 'active_recipe_generation'):
                    state.active_recipe_generation = str(preflight.get('configGeneration', getattr(state, 'active_recipe_generation', '')))
            except (RecipeActivationError, FileNotFoundError) as exc:
                activation = self.recipe_store.mark_activation_start_blocked(recipe_id=recipe_id, batch_id=batch_id, reason=str(exc))
                if state is not None and hasattr(state, 'recipe_activation_state'):
                    state.recipe_activation_state = str(activation.get('activationState', getattr(state, 'recipe_activation_state', '')))
                if state is not None and hasattr(state, 'guidance'):
                    state.guidance = f'启动前配方校验失败：{exc}'
                return False, f'启动前配方校验失败：{exc}'
        result = self._node.call_start()
        if result and result[0] and self.recipe_store is not None and recipe_id:
            try:
                activation = self.recipe_store.mark_activation_start_requested(recipe_id=recipe_id, batch_id=batch_id)
                if state is not None and hasattr(state, 'recipe_activation_state'):
                    state.recipe_activation_state = str(activation.get('activationState', ''))
                    if hasattr(state, 'active_recipe_version'):
                        state.active_recipe_version = str(activation.get('recipeVersion', getattr(state, 'active_recipe_version', '')))
                    if hasattr(state, 'active_recipe_generation'):
                        state.active_recipe_generation = str(activation.get('configGeneration', getattr(state, 'active_recipe_generation', '')))
                if state is not None and hasattr(state, 'guidance'):
                    state.guidance = '启动请求已下发，等待运行链确认当前激活配方。'
            except Exception:
                pass
        return result

    def publish_control(self, action: str) -> None:
        self._node.publish_control(action)

    def request_capture(self, payload: dict[str, Any]) -> bool:
        handler = getattr(self._node, 'request_capture', None)
        return bool(handler(payload)) if callable(handler) else False

    def reset_fault(self) -> tuple[bool, str]:
        return self._node.reset_fault()

    def new_batch(self) -> str:
        return self._node.new_batch()

    def run_diagnostic_action(self, action: str) -> dict[str, Any]:
        return self._node.run_diagnostic_action(action)


@dataclass
class GatewayAppContext:
    runtime: Any
    log_root: Path
    recipe_root: Path
    frontend_dist: Path
    metadata_repository: MetadataRepository
    auth_service: AuthService
    _action_job_service: Any | None = None
    _app_adapter: Any | None = None

    def node(self) -> Any:
        node = getattr(self.runtime, 'node', None)
        if node is None:
            raise RuntimeError('Gateway runtime is not ready.')
        return node

    def app(self) -> Any:
        """Return the gateway application facade behind the ROS composition root."""
        if self._app_adapter is not None:
            return self._app_adapter
        node = self.node()
        app = getattr(node, 'app', None)
        if app is not None:
            self._app_adapter = app
            return app
        self._app_adapter = _LegacyNodeFacadeAdapter(node)
        return self._app_adapter

    def export_service(self) -> BatchExportService:
        app = self.app()
        return BatchExportService(log_root=self.log_root, result_store=app.result_store, recipe_store=app.recipe_store)

    def replay_service(self) -> ReplayService:
        return ReplayService(self.log_root)

    def action_job_service(self):
        if self._action_job_service is None:
            from ..action_job_service import ActionJobService

            self._action_job_service = ActionJobService(self)
            try:
                node = self.node()
                node.register_action_jobs(
                    submit=lambda kind, payload, actor: self._action_job_service.submit(kind, payload=payload, actor=actor),
                    get_job=self._action_job_service.get_job,
                    cancel=lambda job_id, actor: self._action_job_service.cancel(job_id, actor=actor),
                )
                if hasattr(node, 'register_action_executor_updates'):
                    node.register_action_executor_updates(self._action_job_service.handle_executor_update)
            except Exception as exc:
                LOGGER.exception('Failed to register action job callbacks with gateway runtime.', exc_info=exc)
                try:
                    self.audit(actor='system', role='system', action='ACTION_JOB_REGISTRATION_FAILED', resource='/actions/jobs', result='FAILED', details={'error': str(exc)})
                except Exception:
                    LOGGER.debug('Failed to persist ACTION_JOB_REGISTRATION_FAILED audit event.')
        return self._action_job_service


    @property
    def audit_repository(self):
        return self.metadata_repository.audit_repository

    @property
    def session_repository(self):
        return self.metadata_repository.session_repository

    @property
    def export_job_repository(self):
        return self.metadata_repository.export_job_repository

    @property
    def action_job_repository(self):
        return self.metadata_repository.action_job_repository

    def close(self) -> None:
        service = self._action_job_service
        if service is not None and hasattr(service, 'shutdown'):
            try:
                service.shutdown()
            except Exception:
                pass

    def audit(
        self,
        *,
        actor: str,
        role: str,
        action: str,
        resource: str,
        result: str = 'SUCCESS',
        details: dict[str, Any] | None = None,
        correlation_id: str = '',
    ) -> None:
        self.audit_repository.append(
            {
                'ts': utc_now(),
                'actor': actor,
                'role': role,
                'action': action,
                'resource': resource,
                'result': result,
                'correlationId': correlation_id or get_request_id(),
                'details': details or {},
            }
        )
