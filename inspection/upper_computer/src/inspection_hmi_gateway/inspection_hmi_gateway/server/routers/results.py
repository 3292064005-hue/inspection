from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...read_model_repository import ReadModelSyncRequiredError
from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok, page_meta
from ..results.query_services import ResultQueryService
from ..results.command_services import ResultCommandService

router = APIRouter(tags=['results'])


def service(context: GatewayAppContext = Depends(get_context)) -> ResultQueryService:
    return ResultQueryService(context)


def command_service(context: GatewayAppContext = Depends(get_context)) -> ResultCommandService:
    return ResultCommandService(context)


@router.get('/results')
async def get_results(
    batchId: str = '',
    recipeId: str = '',
    decision: str = '',
    defectType: str = '',
    qrText: str = '',
    from_: str = Query('', alias='from'),
    to: str = '',
    limit: int = Query(default=100, ge=1, le=5000),
    offset: int = Query(default=0, ge=0),
    svc: ResultQueryService = Depends(service),
    _session: dict = Depends(require_role('viewer')),
) -> dict:
    try:
        items, total = svc.query(
            batch_id=batchId,
            recipe_id=recipeId,
            decision=decision,
            defect_type=defectType,
            qr_text=qrText,
            from_ts=from_,
            to_ts=to,
            limit=limit,
            offset=offset,
        )
    except ReadModelSyncRequiredError as exc:
        raise HTTPException(status_code=503, detail={'message': str(exc), 'readModelStatus': svc.read_model_status()}) from exc
    return api_ok(items, meta=page_meta(limit=limit, offset=offset, total=total))


@router.post('/results/read-model/repair')
async def repair_read_model(svc: ResultCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    try:
        return api_ok(svc.repair_read_model(actor=session), message='read_model_repaired')
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get('/results/read-model/status')
async def get_read_model_status(svc: ResultQueryService = Depends(service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.read_model_status())


@router.get('/results/summary/{batch_id}')
async def get_result_summary(batch_id: str, svc: ResultQueryService = Depends(service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.summary(batch_id=batch_id))


@router.get('/results/{result_id}')
async def get_result_detail(result_id: str, svc: ResultQueryService = Depends(service), _session: dict = Depends(require_role('viewer'))) -> dict:
    try:
        payload = svc.detail(result_id)
    except ReadModelSyncRequiredError as exc:
        raise HTTPException(status_code=503, detail={'message': str(exc), 'readModelStatus': svc.read_model_status()}) from exc
    if payload is None:
        raise HTTPException(status_code=404, detail='Result not found')
    return api_ok(payload)
