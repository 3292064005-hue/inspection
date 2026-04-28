from __future__ import annotations

from typing import Any

from ..context import GatewayAppContext
from ..service_common import query_plane, recipe_plane


class ResultQueryService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def _normalize_row(self, row: dict[str, Any], *, recipes: dict[str, dict[str, Any]]) -> dict[str, Any]:
        boundary_query = query_plane(self.context).results
        payload = dict(row)
        recipe = recipes.get(payload.get('recipeId', ''), {})
        payload['recipeName'] = str(recipe.get('name', payload.get('recipeId', '')))
        payload['imageUrl'] = boundary_query.artifact_url(str(payload.get('imagePath', '')))
        payload['overlayUrl'] = boundary_query.artifact_url(str(payload.get('overlayPath', '')))
        payload['artifacts'] = [{**artifact, 'url': boundary_query.artifact_url(str(artifact.get('path', '')))} for artifact in payload.get('artifacts', []) if isinstance(artifact, dict)]
        trace_bundle = payload.get('traceBundle')
        if isinstance(trace_bundle, dict):
            trace_bundle = dict(trace_bundle)
            trace_bundle['artifacts'] = [{**artifact, 'url': boundary_query.artifact_url(str(artifact.get('path', '')))} for artifact in trace_bundle.get('artifacts', []) if isinstance(artifact, dict)]
            payload['traceBundle'] = trace_bundle
        payload.pop('imagePath', None)
        payload.pop('overlayPath', None)
        return payload

    def query(self, **filters: Any) -> tuple[list[dict[str, Any]], int]:
        recipes = {item['id']: item for item in recipe_plane(self.context).service.refresh_recipes()}
        items, total = query_plane(self.context).results.query_results(**filters)
        return [self._normalize_row(row, recipes=recipes) for row in items], total

    def detail(self, result_id: str) -> dict[str, Any] | None:
        recipes = {item['id']: item for item in recipe_plane(self.context).service.refresh_recipes()}
        row = query_plane(self.context).results.result_detail(result_id)
        if row is None:
            return None
        return self._normalize_row(row, recipes=recipes)

    def summary(self, *, batch_id: str) -> dict[str, Any]:
        return query_plane(self.context).results.batch_summary(batch_id=batch_id)

    def result_statistics(self, **filters: Any) -> dict[str, Any]:
        recipes = {item['id']: item for item in recipe_plane(self.context).service.refresh_recipes()}
        payload = query_plane(self.context).results.result_statistics(**filters)
        for item in payload.get('recipeBreakdown', []):
            if isinstance(item, dict):
                recipe = recipes.get(str(item.get('recipeId', '')), {})
                item['recipeName'] = str(recipe.get('name', item.get('recipeId', '')))
        for item in payload.get('cycleTrend', []):
            if isinstance(item, dict):
                recipe = recipes.get(str(item.get('recipeId', '')), {})
                item['recipeName'] = str(recipe.get('name', item.get('recipeName', item.get('recipeId', ''))))
        return payload

    def read_model_status(self) -> dict[str, Any]:
        return query_plane(self.context).results.read_model_status()
