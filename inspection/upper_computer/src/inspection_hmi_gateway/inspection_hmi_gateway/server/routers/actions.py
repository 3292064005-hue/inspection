from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..responses import api_ok, page_meta
from ..router_support import raise_action_http_error
from ..operations.query_services import ActionQueryService
from ..operations.command_services import ActionCommandService

router = APIRouter(tags=['actions'])


def query_service(context: GatewayAppContext = Depends(get_context)) -> ActionQueryService:
    return ActionQueryService(context)


def command_service(context: GatewayAppContext = Depends(get_context)) -> ActionCommandService:
    return ActionCommandService(context)


def _submit_action(kind: str, payload: dict, svc: ActionCommandService, session: dict) -> dict:
    """Submit an action job through the persisted action plane.

    Args:
        kind: Normalized action kind registered in the action catalog.
        payload: HTTP-decoded request body.
        svc: Bound command service.
        session: Authenticated actor payload.

    Returns:
        API success envelope payload containing the queued job record.

    Raises:
        HTTPException: Transport-specific validation / policy mapping.
    """
    try:
        return api_ok(svc.submit(kind, payload, actor=session), message='action_job_created')
    except Exception as exc:
        raise_action_http_error(exc, invalid_status=400, runtime_status=409, runtime_code='action_execution_failed')


@router.get('/actions/catalog')
async def get_action_catalog(include_non_production: bool = Query(default=False), svc: ActionQueryService = Depends(query_service), _session: dict = Depends(require_role('viewer'))) -> dict:
    return api_ok(svc.catalog(include_non_production=include_non_production))


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
    return _submit_action('start_batch', payload, svc, session)


@router.post('/actions/reset-station')
async def reset_station(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    return _submit_action('reset_station', payload, svc, session)


@router.post('/actions/run-calibration')
async def run_calibration(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    return _submit_action('run_calibration', payload, svc, session)


@router.post('/actions/execute-replay')
async def execute_replay(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('viewer'))) -> dict:
    return _submit_action('execute_replay', payload, svc, session)


@router.post('/actions/export-batch')
async def export_batch(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    return _submit_action('export_batch', payload, svc, session)


@router.post('/actions/run-benchmark')
async def run_benchmark(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    return _submit_action('run_benchmark', payload, svc, session)


@router.post('/actions/switch-recipe')
async def switch_recipe(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('process_engineer'))) -> dict:
    return _submit_action('switch_recipe_with_validation', payload, svc, session)


@router.post('/actions/stop-station')
async def stop_station(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    return _submit_action('stop_station', payload, svc, session)


@router.post('/actions/set-maintenance-mode')
async def set_maintenance_mode(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    return _submit_action('set_maintenance_mode', payload, svc, session)


@router.post('/actions/create-batch')
async def create_batch(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('operator'))) -> dict:
    return _submit_action('create_batch', payload, svc, session)


@router.post('/actions/diagnostics/capture-frame')
async def diagnostic_capture_frame(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    return _submit_action('diagnostic_capture_frame', payload, svc, session)


@router.post('/actions/diagnostics/test-lighting')
async def diagnostic_test_lighting(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    return _submit_action('diagnostic_test_lighting', payload, svc, session)


@router.post('/actions/diagnostics/test-sort-actuator')
async def diagnostic_test_sort_actuator(payload: dict, svc: ActionCommandService = Depends(command_service), session: dict = Depends(require_role('maintainer'))) -> dict:
    return _submit_action('diagnostic_test_sort_actuator', payload, svc, session)
