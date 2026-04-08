from __future__ import annotations

from typing import Any

from ..context import GatewayAppContext
from ..service_common import app_facade
from ...action_contract import action_catalog


class DiagnosticsQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def list(self) -> list[dict[str, Any]]:
        return app_facade(self.context).diagnostic_items()


class ActionQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def catalog(self, *, include_non_production: bool = False) -> list[dict[str, Any]]:
        runtime_health = self.context.runtime.health() if hasattr(self.context.runtime, 'health') and callable(self.context.runtime.health) else {}
        action_execution = runtime_health.get('actionExecution', {}) if isinstance(runtime_health, dict) else {}
        deployment = {
            'runtimeReady': bool(runtime_health.get('runtimeReady', False)) if isinstance(runtime_health, dict) else False,
            'transportMode': str(action_execution.get('transportMode', 'local_runtime')),
            'transportReady': bool(action_execution.get('transportReady', False)),
            'actionExecutorExpected': bool(action_execution.get('actionExecutorExpected', False)),
            'nativeActionClientEnabled': bool(action_execution.get('nativeActionClientEnabled', False)),
            'executorUpdateChannelBound': bool(action_execution.get('executorUpdateChannelBound', False)),
            'receivedExecutorUpdates': int(action_execution.get('receivedExecutorUpdates', 0)),
            'transportObserved': bool(action_execution.get('transportObserved', False)),
        }
        return [{**item, 'deployment': dict(deployment)} for item in action_catalog(include_non_production=include_non_production)]

    def list_jobs(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return self.context.action_job_repository.list(limit=limit, offset=offset)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.context.action_job_repository.get(job_id)
