from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok
from ..query_services import StationQueryService
from ..command_services import StationCommandService

router = APIRouter(tags=['station'])


def query_service(context: GatewayAppContext = Depends(get_context)) -> StationQueryService:
    return StationQueryService(context)


def command_service(context: GatewayAppContext = Depends(get_context)) -> StationCommandService:
    return StationCommandService(context)


@router.get('/station/snapshot')
async def station_snapshot(svc: StationQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.get_snapshot())


@router.get('/station/stats')
async def station_stats(svc: StationQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.get_stats())


@router.post('/station/start')
async def station_start(svc: StationCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    try:
        return api_ok(svc.start(actor=session))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post('/station/stop')
async def station_stop(svc: StationCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    return api_ok(svc.stop(actor=session))


@router.post('/station/reset-fault')
async def reset_fault(svc: StationCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    try:
        return api_ok(svc.reset_fault(actor=session))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post('/station/new-batch')
async def new_batch(svc: StationCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    return api_ok(svc.new_batch(actor=session))
