from __future__ import annotations

from fastapi import APIRouter, Depends

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok
from ..operations.query_services import DiagnosticsQueryService

router = APIRouter(tags=['diagnostics'])


def query_service(context: GatewayAppContext = Depends(get_context)) -> DiagnosticsQueryService:
    return DiagnosticsQueryService(context)


@router.get('/diagnostics', operation_id='getDiagnosticsSnapshot', summary='Get diagnostics items')
async def get_diagnostics(svc: DiagnosticsQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    """Return the projected diagnostics snapshot.

    Args:
        svc: Bound diagnostics query service.
        _session: Authenticated viewer session.

    Returns:
        Standard API envelope containing projected diagnostics items.

    Raises:
        No route-specific exception is intentionally raised.

    Boundary behavior:
        Diagnostics mutations must use the canonical action plane under
        ``/api/v1/actions/diagnostics/*``. The legacy rollback façade has been
        removed.
    """
    return api_ok(svc.list())
