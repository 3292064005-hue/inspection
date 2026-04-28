from __future__ import annotations

"""Internal-only action endpoints excluded from public API clients.

The routes in this module are intentionally mounted under ``/api/internal`` and
excluded from OpenAPI schema generation. They are used for QA and release
engineering workflows that must not appear in the operator-facing public action
surface.
"""

from fastapi import APIRouter, Depends

from ..context import GatewayAppContext
from ..dependencies import get_context, require_role
from ..operations.command_services import ActionCommandService
from ..responses import api_ok
from ..router_support import raise_action_http_error
from ..schemas import RunBenchmarkRequest

router = APIRouter(tags=['internal-actions'], include_in_schema=False)


def command_service(context: GatewayAppContext = Depends(get_context)) -> ActionCommandService:
    """Return the action command service bound to the current gateway context."""
    return ActionCommandService(context)


@router.post('/actions/run-benchmark', summary='Submit the internal synthetic benchmark action')
async def run_benchmark_internal(
    payload: RunBenchmarkRequest,
    svc: ActionCommandService = Depends(command_service),
    session: dict = Depends(require_role('maintainer')),
) -> dict:
    """Submit the synthetic benchmark through an internal QA namespace.

    Args:
        payload: Benchmark configuration request.
        svc: Action command service.
        session: Authenticated maintainer/admin session.

    Returns:
        API success envelope containing the created action job.

    Raises:
        HTTPException: Raised through ``raise_action_http_error`` when the
        canonical action plane rejects the request or runtime transport.

    Boundary behavior:
        This route is not included in public OpenAPI or generated frontend
        clients. It still uses the action job plane so audit, cancellation, and
        policy behavior remain identical to public actions.
    """
    try:
        return api_ok(svc.submit('run_benchmark', payload.to_payload(), actor=session), message='internal_action_job_created')
    except Exception as exc:
        raise_action_http_error(exc, invalid_status=400, runtime_status=409, runtime_code='action_execution_failed')
