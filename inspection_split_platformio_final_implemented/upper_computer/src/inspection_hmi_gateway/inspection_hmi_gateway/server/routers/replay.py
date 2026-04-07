from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok, page_ok

router = APIRouter(tags=['replay'])


def service(context: GatewayAppContext = Depends(get_context)):
    return context.replay_service()


@router.get('/replay/traces')
async def list_traces(
    batch_id: str = Query(default=''),
    decision: str = Query(default=''),
    q: str = Query(default=''),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    svc=Depends(service),
    _session: dict = Depends(require_role('viewer')),
) -> dict:
    items, total = svc.list_traces(batch_id=batch_id, decision=decision, q=q, limit=limit, offset=offset)
    return page_ok(items, total=total, limit=limit, offset=offset)


@router.get('/replay/traces/{trace_id}')
async def get_trace(trace_id: str, svc=Depends(service), _session: dict = Depends(require_role('viewer'))) -> dict:
    payload = svc.get_trace(trace_id)
    if payload.get('status') == 'MISSING':
        raise HTTPException(status_code=404, detail='Trace not found')
    return api_ok(payload)


@router.get('/replay/traces/{trace_id}/compare')
async def compare_trace(trace_id: str, svc=Depends(service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.compare_trace(trace_id))
