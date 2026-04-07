from __future__ import annotations

from fastapi import APIRouter, Depends

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok
from ..query_services import DiagnosticsQueryService
from ..command_services import DiagnosticsCommandService

router = APIRouter(tags=['diagnostics'])


def query_service(context: GatewayAppContext = Depends(get_context)) -> DiagnosticsQueryService:
    return DiagnosticsQueryService(context)


def command_service(context: GatewayAppContext = Depends(get_context)) -> DiagnosticsCommandService:
    return DiagnosticsCommandService(context)


@router.get('/diagnostics')
async def get_diagnostics(svc: DiagnosticsQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.list())


@router.post('/diagnostics/actions')
async def run_diagnostics_action(payload: dict, svc: DiagnosticsCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    action = str(payload.get('action', ''))
    return api_ok(svc.run_action(action, actor=session))
