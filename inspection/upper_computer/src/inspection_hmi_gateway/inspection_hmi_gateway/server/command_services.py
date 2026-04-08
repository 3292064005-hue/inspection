from __future__ import annotations

import uuid
from typing import Any

from inspection_utils.paths import relative_artifact_path

from .context import GatewayAppContext
from .responses import utc_now
from .service_common import app_facade
from .operations.command_services import ActionCommandService, DiagnosticsCommandService, StationCommandService
from .results.command_services import ResultCommandService


class RecipeCommandService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def save(self, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        recipe = app_facade(self.context).save_recipe(payload)
        self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action='RECIPE_SAVE', resource=f"/recipes/{recipe['id']}", details={'recipeId': recipe['id'], 'version': recipe.get('version', '')})
        return recipe

    def activate(self, recipe_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        receipt = app_facade(self.context).activate_recipe(recipe_id, operator=str(actor.get('username', 'anonymous')))
        self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action='RECIPE_ACTIVATE', resource=f'/recipes/{recipe_id}/activate', details=receipt)
        return receipt


class ExportCommandService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def _record_export(self, *, scope: str, scope_id: str, batch_id: str, artifacts: Any, actor: dict[str, Any]) -> dict[str, Any]:
        relative_path = relative_artifact_path(self.context.log_root, artifacts.export_path)
        payload = {
            'jobId': f"export-{uuid.uuid4().hex[:10]}",
            'scope': scope,
            'scopeId': scope_id,
            'batchId': batch_id,
            'status': 'COMPLETED',
            'createdAt': utc_now(),
            'completedAt': utc_now(),
            'requestedBy': str(actor.get('username', 'anonymous')),
            'exportUrl': f'/artifacts/{relative_path}',
            'itemCount': int(artifacts.item_count),
            'traceCount': int(artifacts.trace_count),
            'details': {'filename': artifacts.export_path.name},
        }
        self.context.metadata_repository.record_export_job(payload)
        self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action=f'EXPORT_{scope.upper()}', resource=f'/exports/{scope}/{scope_id}', details=payload)
        return payload

    def export_batch(self, batch_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        artifacts = self.context.export_service().export_batch(batch_id)
        return self._record_export(scope='batch', scope_id=batch_id, batch_id=batch_id, artifacts=artifacts, actor=actor)

    def export_result(self, result_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        artifacts = self.context.export_service().export_result(result_id)
        detail = app_facade(self.context).result_detail(result_id) or {}
        batch_id = str(detail.get('batchId', ''))
        return self._record_export(scope='result', scope_id=result_id, batch_id=batch_id, artifacts=artifacts, actor=actor)

    def export_trace(self, trace_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        artifacts = self.context.export_service().export_trace(trace_id)
        detail = app_facade(self.context).result_detail(trace_id) or {}
        batch_id = str(detail.get('batchId', ''))
        return self._record_export(scope='trace', scope_id=trace_id, batch_id=batch_id, artifacts=artifacts, actor=actor)
