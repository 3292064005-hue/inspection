from __future__ import annotations

from fastapi import APIRouter, Depends

from ..context import GatewayAppContext
from ..dependencies import get_context
from ..responses import api_ok

router = APIRouter(tags=['health'])


@router.get('/health')
async def health(context: GatewayAppContext = Depends(get_context)) -> dict:
    runtime = context.runtime
    runtime_health = runtime.health() if hasattr(runtime, 'health') and callable(runtime.health) else {'runtimeReady': getattr(runtime, 'node', None) is not None}
    action_execution = runtime_health.get('actionExecution', {}) if isinstance(runtime_health, dict) else {}
    return api_ok(
        {
            'service': 'inspection-hmi-gateway',
            'runtimeReady': bool(runtime_health.get('runtimeReady', False)),
            'runtime': runtime_health,
            'actionExecution': action_execution,
            'logRoot': str(context.log_root),
            'recipeRoot': str(context.recipe_root),
        }
    )
