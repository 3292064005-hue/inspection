from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .action_contract import ActionPolicyError, action_contract
from .action_workflows import (
    ActionWorkflowRunner,
    benchmark_workflow,
    diagnostic_action_workflow,
    maintenance_mode_workflow,
    reset_station_workflow,
    start_batch_workflow,
    stop_station_workflow,
    switch_recipe_workflow,
)


class UpdateFn(Protocol):
    def __call__(self, job_id: str, **fields: Any) -> None: ...


@dataclass(frozen=True, slots=True)
class ActionExecutionRequest:
    job_id: str
    kind: str
    payload: dict[str, Any]
    actor: dict[str, Any]


class RuntimeSupport(Protocol):
    context: Any

    def _step(self, job_id: str, cancel_flag: Any, update: UpdateFn, *, progress: int, message: str, sleep_sec: float = 0.0) -> None: ...
    def _write_job_report(self, job_id: str, category: str, payload: dict[str, Any]) -> Any: ...
    def _artifact_url(self, path: Any) -> str: ...
    def utc_now(self) -> str: ...
    def relative_artifact_path(self, path: str | Any) -> str: ...


class BaseActionHandler:
    kind: str = ''

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        raise NotImplementedError


class StartBatchHandler(BaseActionHandler):
    kind = 'start_batch'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Start a production batch through the station facade."""
        app = runtime.context.app()
        recipe_id = str(request.payload.get('recipeId', '')).strip()
        batch_id = str(request.payload.get('batchId', '')).strip()
        app_state = getattr(app, 'state', None)
        if not recipe_id and app_state is not None:
            recipe_id = str(getattr(app_state, 'active_recipe_id', '') or '').strip()
        if not batch_id and app_state is not None:
            batch_id = str(getattr(app_state, 'pending_batch_id', '') or getattr(app_state, 'batch_id', '') or '').strip()
        if not batch_id:
            batch_id = str(app.new_batch())
        result_sink: dict[str, Any] = {}
        ActionWorkflowRunner(runtime, cancel_flag, update).run(
            request.job_id,
            *start_batch_workflow(app=app, batch_id=batch_id, recipe_id=recipe_id, result_sink=result_sink),
        )
        ok, message = result_sink.get('_start_result', (False, '启动请求未执行。'))
        if not ok:
            raise RuntimeError(message)
        return {'batchId': batch_id, 'recipeId': recipe_id, 'message': message, 'started': True}


class ResetStationHandler(BaseActionHandler):
    kind = 'reset_station'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Pause the line, clear faults, and optionally resume automation."""
        app = runtime.context.app()
        resume_after = bool(request.payload.get('resumeAfter', False))
        result_sink: dict[str, Any] = {}
        ActionWorkflowRunner(runtime, cancel_flag, update).run(
            request.job_id,
            *reset_station_workflow(app=app, resume_after=resume_after, result_sink=result_sink),
        )
        ok, message = result_sink.get('_reset_result', (False, '故障复位未执行。'))
        if not ok:
            raise RuntimeError(message)
        return {'reset': True, 'resumeAfter': resume_after, 'message': message}


class ExecuteReplayHandler(BaseActionHandler):
    kind = 'execute_replay'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Replay a stored trace and write a comparison report."""
        trace_id = str(request.payload.get('traceId', '')).strip()
        if not trace_id:
            raise ValueError('traceId is required')
        replay_service = runtime.context.replay_service()
        runtime._step(request.job_id, cancel_flag, update, progress=25, message='装载回放记录。')
        detail = replay_service.get_trace(trace_id)
        if str(detail.get('status', '')) == 'MISSING':
            raise ValueError('trace_not_found')
        runtime._step(request.job_id, cancel_flag, update, progress=65, message='执行对比分析。')
        comparison = replay_service.compare_trace(trace_id)
        report_path = runtime._write_job_report(request.job_id, 'replay', {'trace': detail, 'comparison': comparison})
        return {'traceId': trace_id, 'trace': detail, 'comparison': comparison, 'reportUrl': runtime._artifact_url(report_path)}


class ExportBatchHandler(BaseActionHandler):
    kind = 'export_batch'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Export a batch bundle and persist the resulting artifact metadata."""
        batch_id = str(request.payload.get('batchId', '')).strip()
        if not batch_id:
            raise ValueError('batchId is required')
        runtime._step(request.job_id, cancel_flag, update, progress=20, message='收集批次结果。')
        export_service = runtime.context.export_service()
        artifacts = export_service.export_batch(batch_id)
        export_relative_path = runtime.relative_artifact_path(artifacts.export_path)
        export_payload = {
            'jobId': f"export-{request.job_id.split('-', 1)[-1]}",
            'batchId': batch_id,
            'status': 'COMPLETED',
            'createdAt': runtime.utc_now(),
            'completedAt': runtime.utc_now(),
            'requestedBy': str(request.actor.get('username', 'anonymous')),
            'exportUrl': f'/artifacts/{export_relative_path}',
            'itemCount': int(artifacts.item_count),
            'traceCount': int(artifacts.trace_count),
            'details': {'filename': artifacts.export_path.name, 'sourceActionJobId': request.job_id},
        }
        metadata_repository = getattr(runtime.context, 'metadata_repository', None)
        if metadata_repository is not None and hasattr(metadata_repository, 'record_export_job'):
            metadata_repository.record_export_job(export_payload)
        runtime._step(request.job_id, cancel_flag, update, progress=85, message='批次导出完成。')
        return export_payload


class RunBenchmarkHandler(BaseActionHandler):
    kind = 'run_benchmark'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Run the explicitly synthetic benchmark workflow.

        Args:
            runtime: Shared action runtime services.
            request: Normalized action execution request.
            cancel_flag: Cooperative cancellation flag.
            update: Job-state publisher.

        Returns:
            Synthetic benchmark metadata and report URL.

        Raises:
            No action-specific exception is raised beyond runtime or transport
            failures encountered by the shared runtime helpers.

        Boundary behavior:
            This handler intentionally tags its report and result payload as
            synthetic so upstream consumers cannot mistake it for production
            inspection evidence.
        """
        app = runtime.context.app()
        try:
            samples = max(1, int(request.payload.get('sampleCount', 10) or 10))
        except (TypeError, ValueError):
            samples = 10
        capability = action_contract(self.kind).capability.to_dict()
        ActionWorkflowRunner(runtime, cancel_flag, update).run(
            request.job_id,
            *benchmark_workflow(app=app),
        )
        report_path = runtime._write_job_report(
            request.job_id,
            'benchmark',
            {
                'sampleCount': samples,
                'completedAt': runtime.utc_now(),
                'mode': 'synthetic',
                'capability': capability,
            },
        )
        return {
            'sampleCount': samples,
            'reportUrl': runtime._artifact_url(report_path),
            'benchmarkCompleted': True,
            'executionClass': 'synthetic',
            'capability': capability,
        }


class SwitchRecipeWithValidationHandler(BaseActionHandler):
    kind = 'switch_recipe_with_validation'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Validate a recipe and optionally activate it as the new default."""
        app = runtime.context.app()
        recipe_id = str(request.payload.get('recipeId', '')).strip()
        if not recipe_id:
            raise ValueError('recipeId is required')
        dry_run = bool(request.payload.get('dryRun', False))
        result_sink: dict[str, Any] = {}
        ActionWorkflowRunner(runtime, cancel_flag, update).run(
            request.job_id,
            *switch_recipe_workflow(app=app, recipe_id=recipe_id, dry_run=dry_run, actor=str(request.actor.get('username', 'anonymous')), result_sink=result_sink),
        )
        return {
            'recipeId': recipe_id,
            'dryRun': dry_run,
            'validation': dict(result_sink.get('validation', {})),
            'activation': dict(result_sink.get('activation', {})),
        }


class StopStationHandler(BaseActionHandler):
    kind = 'stop_station'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Stop the station through the canonical control plane."""
        app = runtime.context.app()
        ActionWorkflowRunner(runtime, cancel_flag, update).run(
            request.job_id,
            *stop_station_workflow(app=app),
        )
        return {'stopped': True, 'message': '已发布停止指令。'}


class SetMaintenanceModeHandler(BaseActionHandler):
    kind = 'set_maintenance_mode'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Request a maintenance-mode transition through the canonical action plane."""
        enabled = bool(request.payload.get('enabled', False))
        result_sink: dict[str, Any] = {}
        ActionWorkflowRunner(runtime, cancel_flag, update).run(
            request.job_id,
            *maintenance_mode_workflow(app=runtime.context.app(), enabled=enabled, actor=str(request.actor.get('username', 'anonymous')), result_sink=result_sink),
        )
        return dict(result_sink.get('snapshot', {}))


class CreateBatchHandler(BaseActionHandler):
    kind = 'create_batch'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Allocate a new batch identifier through the canonical action plane."""
        runtime._step(request.job_id, cancel_flag, update, progress=25, message='申请新批次号。')
        batch_id = str(runtime.context.app().new_batch())
        runtime._step(request.job_id, cancel_flag, update, progress=90, message='新批次号已分配。')
        return {'batchId': batch_id}


class DiagnosticActionProxyHandler(BaseActionHandler):
    """Execute a maintenance-only diagnostic action through the app facade.

    Args:
        runtime: Shared action runtime services.
        request: Normalized action execution request.
        cancel_flag: Cooperative cancellation flag.
        update: Job-state publisher.

    Returns:
        Diagnostic execution result payload.

    Raises:
        RuntimeError: When the gateway runtime rejects the diagnostic action.

    Boundary behavior:
        The handler reuses the production diagnostic service so maintenance
        guards, auditing, and projection side effects stay consistent.
    """

    diagnostic_action: str = ''

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        app = runtime.context.app()
        result_sink: dict[str, Any] = {}
        ActionWorkflowRunner(runtime, cancel_flag, update).run(
            request.job_id,
            *diagnostic_action_workflow(app=app, diagnostic_action=self.diagnostic_action, result_sink=result_sink),
        )
        return dict(result_sink.get('result', {}))


class DiagnosticCaptureFrameHandler(DiagnosticActionProxyHandler):
    kind = 'diagnostic_capture_frame'
    diagnostic_action = 'CAPTURE_FRAME'


class DiagnosticTestLightingHandler(DiagnosticActionProxyHandler):
    kind = 'diagnostic_test_lighting'
    diagnostic_action = 'TEST_LIGHTING'


class DiagnosticTestSortActuatorHandler(DiagnosticActionProxyHandler):
    kind = 'diagnostic_test_sort_actuator'
    diagnostic_action = 'TEST_SORT_ACTUATOR'


ACTION_HANDLER_REGISTRY: dict[str, BaseActionHandler] = {
    handler.kind: handler for handler in (
        StartBatchHandler(),
        ResetStationHandler(),
        ExecuteReplayHandler(),
        ExportBatchHandler(),
        RunBenchmarkHandler(),
        SwitchRecipeWithValidationHandler(),
        StopStationHandler(),
        SetMaintenanceModeHandler(),
        CreateBatchHandler(),
        DiagnosticCaptureFrameHandler(),
        DiagnosticTestLightingHandler(),
        DiagnosticTestSortActuatorHandler(),
    )
}
