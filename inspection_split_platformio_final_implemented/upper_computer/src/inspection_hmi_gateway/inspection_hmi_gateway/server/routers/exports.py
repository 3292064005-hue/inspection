from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok
from ..query_services import ExportQueryService
from ..command_services import ExportCommandService

router = APIRouter(tags=['exports'])


def query_service(context: GatewayAppContext = Depends(get_context)) -> ExportQueryService:
    return ExportQueryService(context)


def command_service(context: GatewayAppContext = Depends(get_context)) -> ExportCommandService:
    return ExportCommandService(context)


@router.post('/exports/{batch_id}')
async def export_batch(batch_id: str, svc: ExportCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    try:
        return api_ok(svc.export_batch(batch_id, actor=session))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/exports/results/{result_id}')
async def export_result(result_id: str, svc: ExportCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    try:
        return api_ok(svc.export_result(result_id, actor=session))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/exports/traces/{trace_id}')
async def export_trace(trace_id: str, svc: ExportCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    try:
        return api_ok(svc.export_trace(trace_id, actor=session))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get('/exports/jobs/{job_id}')
async def get_export_job(job_id: str, svc: ExportQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    job = svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='导出任务不存在。')
    return api_ok(job)


@router.get('/exports/jobs')
async def list_export_jobs(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    svc: ExportQueryService = Depends(query_service),
    _session: dict = Depends(require_role('viewer')),
) -> dict:
    items, total = svc.list_jobs(limit=limit, offset=offset)
    from ..responses import page_meta
    return api_ok(items, meta=page_meta(limit=limit, offset=offset, total=total))
