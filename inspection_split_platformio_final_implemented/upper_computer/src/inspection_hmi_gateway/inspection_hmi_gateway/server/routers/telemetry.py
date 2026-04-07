from __future__ import annotations

from fastapi import APIRouter, Depends

from ..dependencies import require_role
from ..responses import api_ok
from ..query_services import TelemetryGatewayQueryService
from ..context import GatewayAppContext
from ..dependencies import get_context

router = APIRouter(tags=['telemetry'])


def service(context: GatewayAppContext = Depends(get_context)) -> TelemetryGatewayQueryService:
    return TelemetryGatewayQueryService(context)


@router.get('/telemetry/bridges')
async def list_telemetry_bridges(svc: TelemetryGatewayQueryService = Depends(service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.list_bridges())
