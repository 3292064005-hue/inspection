from __future__ import annotations

from fastapi import APIRouter, Depends

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok
from ..query_services import StationQueryService

router = APIRouter(tags=['station'])


def query_service(context: GatewayAppContext = Depends(get_context)) -> StationQueryService:
    return StationQueryService(context)


@router.get('/station/snapshot', operation_id='getStationSnapshot', summary='Get the station snapshot')
async def station_snapshot(svc: StationQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    """Return the current projected station snapshot."""
    return api_ok(svc.get_snapshot())


@router.get('/station/stats', operation_id='getStationStats', summary='Get station counters')
async def station_stats(svc: StationQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    """Return the current projected station counter payload."""
    return api_ok(svc.get_stats())
