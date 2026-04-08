from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok
from ..router_support import compat_headers, raise_action_http_error
from ..operations.query_services import DiagnosticsQueryService
from ..operations.command_services import DiagnosticsCommandService

router = APIRouter(tags=['diagnostics'])


def query_service(context: GatewayAppContext = Depends(get_context)) -> DiagnosticsQueryService:
    return DiagnosticsQueryService(context)


def command_service(context: GatewayAppContext = Depends(get_context)) -> DiagnosticsCommandService:
    return DiagnosticsCommandService(context)


@router.get('/diagnostics')
async def get_diagnostics(svc: DiagnosticsQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.list())


@router.post('/diagnostics/actions')
async def run_diagnostics_action(payload: dict, response: Response, svc: DiagnosticsCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    """Run a legacy diagnostics action through the canonical action plane.

    Args:
        payload: Legacy request payload containing ``action``.
        response: FastAPI response used to expose compatibility headers.
        svc: Bound diagnostics command service.
        session: Authenticated actor metadata.

    Returns:
        Legacy-compatible diagnostics result payload.

    Raises:
        HTTPException: Structured validation, policy, dispatch, or terminal-job
            failures mapped from the canonical action plane.
    """
    headers = compat_headers(route='/api/v1/diagnostics/actions')
    response.headers.update(headers)
    action = str(payload.get('action', ''))
    try:
        return api_ok(svc.run_action(action, actor=session))
    except Exception as exc:
        raise_action_http_error(exc, invalid_status=400, runtime_status=409, runtime_code='diagnostic_action_failed', headers=headers)
