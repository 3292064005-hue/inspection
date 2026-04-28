from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok, page_meta
from ..query_services import AuditQueryService

router = APIRouter(tags=['audit'])


def service(context: GatewayAppContext = Depends(get_context)) -> AuditQueryService:
    return AuditQueryService(context)


@router.get('/audit', operation_id='getAuditEntries')
async def get_audit(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    svc: AuditQueryService = Depends(service),
    _session: dict = Depends(require_role('admin')),
) -> dict:
    items, total = svc.list(limit=limit, offset=offset)
    return api_ok(items, meta=page_meta(limit=limit, offset=offset, total=total))
