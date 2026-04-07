from __future__ import annotations

import uuid
from typing import Any

from inspection_utils.control_protocol import STOP_COMMAND
from inspection_utils.paths import relative_artifact_path

from .context import GatewayAppContext
from .responses import utc_now
from .service_common import app_facade


class StationCommandService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def start(self, *, actor: dict[str, Any]) -> dict[str, Any]:
        ok, message = app_facade(self.context).call_start()
        self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action='STATION_START', resource='/station', result='SUCCESS' if ok else 'FAILED', details={'message': message})
        if not ok:
            raise RuntimeError(message)
        return {'success': True, 'message': message}

    def stop(self, *, actor: dict[str, Any]) -> dict[str, Any]:
        app_facade(self.context).publish_control(STOP_COMMAND)
        self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action='STATION_STOP', resource='/station', details={})
        return {'success': True, 'message': '已发布停止指令。'}

    def reset_fault(self, *, actor: dict[str, Any]) -> dict[str, Any]:
        ok, message = app_facade(self.context).reset_fault()
        self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action='FAULT_RESET', resource='/station/fault', result='SUCCESS' if ok else 'FAILED', details={'message': message})
        if not ok:
            raise RuntimeError(message)
        return {'success': True, 'message': message}

    def new_batch(self, *, actor: dict[str, Any]) -> dict[str, Any]:
        batch_id = app_facade(self.context).new_batch()
        self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action='BATCH_NEW', resource='/station/batch', details={'batchId': batch_id})
        return {'batchId': batch_id}


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


class DiagnosticsCommandService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def run_action(self, action: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        result = app_facade(self.context).run_diagnostic_action(action)
        self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action=f'DIAGNOSTIC_{str(action).upper()}', resource='/diagnostics/actions', result='SUCCESS' if result.get('success') else 'FAILED', details=result)
        return result


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


class ActionCommandService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def submit(self, kind: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        return self.context.action_job_service().submit(kind, payload=payload, actor=actor)

    def cancel(self, job_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        return self.context.action_job_service().cancel(job_id, actor=actor)
