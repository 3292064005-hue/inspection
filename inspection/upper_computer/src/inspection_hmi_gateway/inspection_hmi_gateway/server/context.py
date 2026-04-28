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


_request_id: ContextVar[str] = ContextVar('inspection_gateway_request_id', default='')

LOGGER = logging.getLogger(__name__)


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str:
    return _request_id.get()


@dataclass
class GatewayAppContext:
    runtime: Any
    log_root: Path
    recipe_root: Path
    frontend_dist: Path
    telemetry_config_path: Path
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
        """Return the gateway runtime application service behind the ROS composition root.

        Args:
            None.

        Returns:
            The gateway application service used by HTTP handlers and services.

        Raises:
            RuntimeError: When the runtime does not expose the explicit
                application service expected by the gateway HTTP layer.

        Boundary behavior:
            Production runtime composition must expose the explicit ``app``
            service object so HTTP handlers, websocket bootstrapping, and
            action jobs all bind to the same business boundary.
        """
        if self._app_adapter is not None:
            return self._app_adapter
        node = self.node()
        app = getattr(node, 'app', None)
        if app is None:
            raise RuntimeError('Gateway runtime must expose the application service.')
        self._app_adapter = app
        return app

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
