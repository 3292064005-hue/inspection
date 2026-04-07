from __future__ import annotations

from typing import Any

from ..telemetry_service import TelemetryService
from .context import GatewayAppContext
from .service_common import app_facade


class StationQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def get_snapshot(self) -> dict[str, Any]:
        return app_facade(self.context).snapshot_payload()

    def get_stats(self) -> dict[str, Any]:
        return app_facade(self.context).stats_payload()


class ResultQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def _normalize_row(self, row: dict[str, Any], *, recipes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        app = app_facade(self.context)
        payload = dict(row)
        recipe = recipes.get(payload.get('recipeId', ''), {})
        payload['recipeName'] = str(recipe.get('name', payload.get('recipeId', '')))
        payload['imageUrl'] = app.artifact_url(str(payload.get('imagePath', '')))
        payload['overlayUrl'] = app.artifact_url(str(payload.get('overlayPath', '')))
        payload['artifacts'] = [
            {**artifact, 'url': app.artifact_url(str(artifact.get('path', '')))}
            for artifact in payload.get('artifacts', [])
            if isinstance(artifact, dict)
        ]
        trace_bundle = payload.get('traceBundle')
        if isinstance(trace_bundle, dict):
            trace_bundle = dict(trace_bundle)
            trace_bundle['artifacts'] = [
                {**artifact, 'url': app.artifact_url(str(artifact.get('path', '')))}
                for artifact in trace_bundle.get('artifacts', [])
                if isinstance(artifact, dict)
            ]
            payload['traceBundle'] = trace_bundle
        payload.pop('imagePath', None)
        payload.pop('overlayPath', None)
        return payload

    def query(self, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        app = app_facade(self.context)
        recipes = {item['id']: item for item in app.refresh_recipes()}
        items, total = app.query_results(**filters)
        return [self._normalize_row(row, recipes=recipes) for row in items], total

    def detail(self, result_id: str) -> dict[str, Any] | None:
        app = app_facade(self.context)
        recipes = {item['id']: item for item in app.refresh_recipes()}
        row = app.result_detail(result_id)
        if row is None:
            return None
        return self._normalize_row(row, recipes=recipes)

    def summary(self, *, batch_id: str) -> dict[str, Any]:
        return app_facade(self.context).batch_summary(batch_id=batch_id)

    def read_model_status(self) -> dict[str, Any]:
        return app_facade(self.context).read_model_status()


class RecipeQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def list(self) -> list[dict[str, Any]]:
        return app_facade(self.context).refresh_recipes()

    def history(self, recipe_id: str) -> dict[str, Any]:
        return app_facade(self.context).recipe_history(recipe_id)


class DiagnosticsQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def list(self) -> list[dict[str, Any]]:
        return app_facade(self.context).diagnostic_items()


class ExportQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def list_jobs(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        items, total = self.context.export_job_repository.list(limit=limit, offset=offset)
        for item in items:
            details = item.get('details', {}) if isinstance(item.get('details', {}), dict) else {}
            export_url = str(item.get('exportUrl', ''))
            if export_url and export_url.startswith('/artifacts/'):
                details['downloadUrl'] = export_url
            item['details'] = details
        return items, total

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        item = self.context.export_job_repository.get(job_id)
        if item is None:
            return None
        details = item.get('details', {}) if isinstance(item.get('details', {}), dict) else {}
        export_url = str(item.get('exportUrl', ''))
        if export_url and export_url.startswith('/artifacts/'):
            details['downloadUrl'] = export_url
            item['details'] = details
        return item


class ReplayGatewayQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def list_items(self, *, batch_id: str, decision: str, q: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return self.context.replay_service().list_traces(batch_id=batch_id, decision=decision, q=q, limit=limit, offset=offset)

    def get_detail(self, trace_id: str) -> dict[str, Any]:
        return self.context.replay_service().get_trace(trace_id)

    def get_compare(self, trace_id: str) -> dict[str, Any]:
        return self.context.replay_service().compare_trace(trace_id)

    def get_bundle(self, trace_id: str) -> dict[str, Any]:
        return self.context.replay_service().get_trace(trace_id)


class ActionQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def catalog(self) -> list[dict[str, Any]]:
        from ..action_contract import action_catalog
        return action_catalog()

    def list_jobs(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return self.context.action_job_repository.list(limit=limit, offset=offset)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.context.action_job_repository.get(job_id)


class TelemetryGatewayQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def list_bridges(self) -> list[dict[str, Any]]:
        config_path = self.context.log_root / 'telemetry_bridges.json'
        return TelemetryService(config_path).list_bridges()


class AuditQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def list(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return self.context.audit_repository.list(limit=limit, offset=offset)
