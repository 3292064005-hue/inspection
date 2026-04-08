from __future__ import annotations

from typing import Any

from ..context import GatewayAppContext
from ..service_common import app_facade


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
        payload['artifacts'] = [{**artifact, 'url': app.artifact_url(str(artifact.get('path', '')))} for artifact in payload.get('artifacts', []) if isinstance(artifact, dict)]
        trace_bundle = payload.get('traceBundle')
        if isinstance(trace_bundle, dict):
            trace_bundle = dict(trace_bundle)
            trace_bundle['artifacts'] = [{**artifact, 'url': app.artifact_url(str(artifact.get('path', '')))} for artifact in trace_bundle.get('artifacts', []) if isinstance(artifact, dict)]
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
