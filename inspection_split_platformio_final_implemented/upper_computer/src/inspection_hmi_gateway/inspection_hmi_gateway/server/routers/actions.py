from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok, page_meta
from ..query_services import ActionQueryService
from ..command_services import ActionCommandService

router = APIRouter(tags=['actions'])


def query_service(context: GatewayAppContext = Depends(get_context)) -> ActionQueryService:
    return ActionQueryService(context)


def command_service(context: GatewayAppContext = Depends(get_context)) -> ActionCommandService:
    return ActionCommandService(context)


@router.get('/actions/catalog')
async def get_action_catalog(svc: ActionQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.catalog())


@router.get('/actions/jobs')
async def list_action_jobs(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    svc: ActionQueryService = Depends(query_service),
    _session: dict = Depends(require_role('viewer')),
) -> dict:
    items, total = svc.list_jobs(limit=limit, offset=offset)
    return api_ok(items, meta=page_meta(limit=limit, offset=offset, total=total))


@router.get('/actions/jobs/{job_id}')
async def get_action_job(job_id: str, svc: ActionQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    job = svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='任务不存在。')
    return api_ok(job)


@router.post('/actions/jobs/{job_id}/cancel')
async def cancel_action_job(job_id: str, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    try:
        return api_ok(svc.cancel(job_id, actor=session))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/actions/start-batch')
async def start_batch(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    try:
        return api_ok(svc.submit('start_batch', payload, actor=session), message='action_job_created')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/actions/reset-station')
async def reset_station(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    try:
        return api_ok(svc.submit('reset_station', payload, actor=session), message='action_job_created')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/actions/run-calibration')
async def run_calibration(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    try:
        return api_ok(svc.submit('run_calibration', payload, actor=session), message='action_job_created')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/actions/execute-replay')
async def execute_replay(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('viewer'))) -> dict:
    try:
        return api_ok(svc.submit('execute_replay', payload, actor=session), message='action_job_created')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/actions/export-batch')
async def export_batch(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    try:
        return api_ok(svc.submit('export_batch', payload, actor=session), message='action_job_created')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/actions/run-benchmark')
async def run_benchmark(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    try:
        return api_ok(svc.submit('run_benchmark', payload, actor=session), message='action_job_created')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/actions/switch-recipe')
async def switch_recipe(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('process_engineer'))) -> dict:
    try:
        return api_ok(svc.submit('switch_recipe_with_validation', payload, actor=session), message='action_job_created')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
