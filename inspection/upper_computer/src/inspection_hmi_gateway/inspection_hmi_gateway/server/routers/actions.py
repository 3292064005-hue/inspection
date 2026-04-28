from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..operations.command_services import ActionCommandService
from ..operations.query_services import ActionQueryService
from ..responses import api_ok, page_meta
from ..router_support import raise_action_http_error
from ..schemas import (
    EmptyActionRequest,
    ExecuteReplayRequest,
    ExportBatchRequest,
    MaintenanceModeRequest,
    ResetStationRequest,
    StartBatchRequest,
    StrictRequestModel,
    SwitchRecipeRequest,
)

router = APIRouter(tags=['actions'])


def query_service(context: GatewayAppContext = Depends(get_context)) -> ActionQueryService:
    return ActionQueryService(context)


def command_service(context: GatewayAppContext = Depends(get_context)) -> ActionCommandService:
    return ActionCommandService(context)


def _submit_action(kind: str, payload: StrictRequestModel, svc: ActionCommandService, session: dict) -> dict:
    """Submit an action job through the persisted public action plane.

    Args:
        kind: Normalized action kind registered in the public action catalog.
        payload: Typed HTTP request model.
        svc: Bound command service.
        session: Authenticated actor payload.

    Returns:
        API success envelope payload containing the queued job record.

    Raises:
        HTTPException: Transport-specific validation / policy mapping.

    Boundary behavior:
        Only declared request fields are forwarded to the action runtime. Any
        unknown JSON key is rejected by the request model before a job record is
        created.
    """
    try:
        return api_ok(svc.submit(kind, payload.to_payload(), actor=session), message='action_job_created')
    except Exception as exc:
        raise_action_http_error(exc, invalid_status=400, runtime_status=409, runtime_code='action_execution_failed')


@router.get('/actions/catalog', operation_id='getActionCatalog', summary='List the public action catalog')
async def get_action_catalog(
    include_non_production: bool = Query(default=False),
    svc: ActionQueryService = Depends(query_service),
    _session: dict = Depends(require_role('viewer')),
) -> dict:
    return api_ok(svc.catalog(include_non_production=include_non_production))


@router.get('/actions/capability-matrix', operation_id='getActionCapabilityMatrix', summary='Get the effective action capability matrix')
async def get_action_capability_matrix(
    svc: ActionQueryService = Depends(query_service),
    _session: dict = Depends(require_role('viewer')),
) -> dict:
    return api_ok(svc.capability_matrix())


@router.get('/actions/jobs', operation_id='listActionJobs', summary='List action jobs')
async def list_action_jobs(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    svc: ActionQueryService = Depends(query_service),
    _session: dict = Depends(require_role('viewer')),
) -> dict:
    items, total = svc.list_jobs(limit=limit, offset=offset)
    return api_ok(items, meta=page_meta(limit=limit, offset=offset, total=total))


@router.get('/actions/jobs/{job_id}', operation_id='getActionJob', summary='Get one action job')
async def get_action_job(
    job_id: str,
    svc: ActionQueryService = Depends(query_service),
    _session: dict = Depends(require_role('viewer')),
) -> dict:
    job = svc.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='任务不存在。')
    return api_ok(job)


@router.post('/actions/jobs/{job_id}/cancel', operation_id='cancelActionJob', summary='Cancel one action job')
async def cancel_action_job(
    job_id: str,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('operator')),
) -> dict:
    try:
        return api_ok(svc.cancel(job_id, actor=session))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post('/actions/start-batch', operation_id='submitStartBatchAction', summary='Submit the start-batch action')
async def start_batch(
    payload: StartBatchRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('operator')),
) -> dict:
    return _submit_action('start_batch', payload, svc, session)


@router.post('/actions/reset-station', operation_id='submitResetStationAction', summary='Submit the reset-station action')
async def reset_station(
    payload: ResetStationRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('maintainer')),
) -> dict:
    return _submit_action('reset_station', payload, svc, session)


@router.post('/actions/execute-replay', operation_id='submitExecuteReplayAction', summary='Submit the trace replay action')
async def execute_replay(
    payload: ExecuteReplayRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('viewer')),
) -> dict:
    return _submit_action('execute_replay', payload, svc, session)


@router.post('/actions/export-batch', operation_id='submitExportBatchAction', summary='Submit the batch export action')
async def export_batch(
    payload: ExportBatchRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('operator')),
) -> dict:
    return _submit_action('export_batch', payload, svc, session)


@router.post('/actions/switch-recipe', operation_id='submitSwitchRecipeAction', summary='Submit the recipe validation and activation action')
async def switch_recipe(
    payload: SwitchRecipeRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('process_engineer')),
) -> dict:
    return _submit_action('switch_recipe_with_validation', payload, svc, session)


@router.post('/actions/stop-station', operation_id='submitStopStationAction', summary='Submit the stop-station action')
async def stop_station(
    payload: EmptyActionRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('operator')),
) -> dict:
    return _submit_action('stop_station', payload, svc, session)


@router.post('/actions/set-maintenance-mode', operation_id='submitMaintenanceModeAction', summary='Submit the maintenance-mode action')
async def set_maintenance_mode(
    payload: MaintenanceModeRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('maintainer')),
) -> dict:
    return _submit_action('set_maintenance_mode', payload, svc, session)


@router.post('/actions/create-batch', operation_id='submitCreateBatchAction', summary='Submit the create-batch action')
async def create_batch(
    payload: EmptyActionRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('operator')),
) -> dict:
    return _submit_action('create_batch', payload, svc, session)


@router.post('/actions/diagnostics/capture-frame', operation_id='submitDiagnosticCaptureFrameAction', summary='Submit the capture-frame diagnostic action')
async def diagnostic_capture_frame(
    payload: EmptyActionRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('maintainer')),
) -> dict:
    return _submit_action('diagnostic_capture_frame', payload, svc, session)


@router.post('/actions/diagnostics/test-lighting', operation_id='submitDiagnosticTestLightingAction', summary='Submit the lighting diagnostic action')
async def diagnostic_test_lighting(
    payload: EmptyActionRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('maintainer')),
) -> dict:
    return _submit_action('diagnostic_test_lighting', payload, svc, session)


@router.post('/actions/diagnostics/test-sort-actuator', operation_id='submitDiagnosticTestSortActuatorAction', summary='Submit the sort-actuator diagnostic action')
async def diagnostic_test_sort_actuator(
    payload: EmptyActionRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('maintainer')),
) -> dict:
    return _submit_action('diagnostic_test_sort_actuator', payload, svc, session)
