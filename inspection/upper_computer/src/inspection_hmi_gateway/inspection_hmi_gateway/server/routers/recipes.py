from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok
from ..router_support import raise_action_http_error
from ..schemas import SaveRecipeRequest
from ..query_services import RecipeQueryService
from ..command_services import RecipeCommandService

router = APIRouter(tags=['recipes'])


def query_service(context: GatewayAppContext = Depends(get_context)) -> RecipeQueryService:
    return RecipeQueryService(context)


def command_service(context: GatewayAppContext = Depends(get_context)) -> RecipeCommandService:
    return RecipeCommandService(context)


@router.get('/recipes', operation_id='getRecipes')
async def get_recipes(svc: RecipeQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.list())


@router.post('/recipes', operation_id='saveRecipe')
async def save_recipe(payload: SaveRecipeRequest, svc: RecipeCommandService = Depends(command_service), session: dict = Depends(require_role('process_engineer'))) -> dict:
    try:
        return api_ok(svc.save(payload.to_payload(), actor=session))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post('/recipes/{recipe_id}/activate', operation_id='activateRecipeDirect', deprecated=True, summary='Deprecated compatibility redirect to switch-recipe action')
async def activate_recipe(recipe_id: str, svc: RecipeCommandService = Depends(command_service), session: dict = Depends(require_role('process_engineer'))) -> dict:
    try:
        return api_ok(svc.activate(recipe_id, actor=session), message='deprecated_route_redirected_to_action_plane')
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise_action_http_error(exc, invalid_status=400, runtime_status=409, runtime_code='recipe_activation_redirect_failed')


@router.get('/recipes/{recipe_id}/history', operation_id='getRecipeHistory')
async def recipe_history(recipe_id: str, svc: RecipeQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.history(recipe_id))
