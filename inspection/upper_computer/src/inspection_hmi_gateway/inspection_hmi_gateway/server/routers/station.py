from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok
from ..router_support import compat_headers, raise_action_http_error
from ..query_services import StationQueryService
from ..command_services import StationCommandService

router = APIRouter(tags=['station'])


class MaintenanceModePayload(BaseModel):
    enabled: bool


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
async def station_start(response: Response, svc: StationCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    headers = compat_headers(route='/api/v1/station/start')
    response.headers.update(headers)
    try:
        return api_ok(svc.start(actor=session))
    except Exception as exc:
        raise_action_http_error(exc, invalid_status=400, runtime_status=503, runtime_code='station_action_failed', headers=headers)


@router.post('/station/stop')
async def station_stop(response: Response, svc: StationCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    headers = compat_headers(route='/api/v1/station/stop')
    response.headers.update(headers)
    try:
        return api_ok(svc.stop(actor=session))
    except Exception as exc:
        raise_action_http_error(exc, invalid_status=400, runtime_status=503, runtime_code='station_action_failed', headers=headers)


@router.post('/station/reset-fault')
async def reset_fault(response: Response, svc: StationCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    headers = compat_headers(route='/api/v1/station/reset-fault')
    response.headers.update(headers)
    try:
        return api_ok(svc.reset_fault(actor=session))
    except Exception as exc:
        raise_action_http_error(exc, invalid_status=400, runtime_status=503, runtime_code='station_action_failed', headers=headers)


@router.post('/station/maintenance')
async def set_maintenance_mode(payload: MaintenanceModePayload, response: Response, svc: StationCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    headers = compat_headers(route='/api/v1/station/maintenance')
    response.headers.update(headers)
    try:
        return api_ok(svc.set_maintenance_mode(payload.enabled, actor=session))
    except Exception as exc:
        raise_action_http_error(exc, invalid_status=400, runtime_status=409, runtime_code='maintenance_action_failed', headers=headers)


@router.post('/station/new-batch')
async def new_batch(response: Response, svc: StationCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    headers = compat_headers(route='/api/v1/station/new-batch')
    response.headers.update(headers)
    try:
        return api_ok(svc.new_batch(actor=session))
    except Exception as exc:
        raise_action_http_error(exc, invalid_status=400, runtime_status=503, runtime_code='station_action_failed', headers=headers)
