from __future__ import annotations

from fastapi import APIRouter, Depends

from ..context import GatewayAppContext
from ..dependencies import get_context
from ..responses import api_ok

router = APIRouter(tags=['health'])


@router.get('/health')
async def health(context: GatewayAppContext = Depends(get_context)) -> dict:
    runtime_ready = getattr(context.runtime, 'node', None) is not None
    return api_ok(
        {
            'service': 'inspection-hmi-gateway',
            'runtimeReady': runtime_ready,
            'logRoot': str(context.log_root),
            'recipeRoot': str(context.recipe_root),
        }
    )
