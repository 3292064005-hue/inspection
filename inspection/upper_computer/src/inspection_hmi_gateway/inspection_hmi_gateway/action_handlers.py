from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .action_contract import ActionPolicyError, action_contract


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
        """Start a production batch through the station facade.

        Args:
            runtime: Shared action runtime services.
            request: Normalized action execution request.
            cancel_flag: Cooperative cancellation flag.
            update: Job-state publisher.

        Returns:
            Result payload persisted onto the action job record.

        Raises:
            RuntimeError: When the station start command is rejected.

        Boundary behavior:
            When ``batchId`` is omitted the handler allocates a new batch id.
        """
        app = runtime.context.app()
        recipe_id = str(request.payload.get('recipeId', '')).strip()
        batch_id = str(request.payload.get('batchId', '')).strip()
        app_state = getattr(app, 'state', None)
        if not recipe_id and app_state is not None:
            recipe_id = str(getattr(app_state, 'active_recipe_id', '') or '').strip()
        if not batch_id and app_state is not None:
            batch_id = str(getattr(app_state, 'pending_batch_id', '') or getattr(app_state, 'batch_id', '') or '').strip()
        runtime._step(request.job_id, cancel_flag, update, progress=15, message='准备批次上下文。')
        if not batch_id:
            batch_id = str(app.new_batch())
        runtime._step(request.job_id, cancel_flag, update, progress=55, message='下发启动请求。')
        ok, message = app.call_start(recipe_id=recipe_id, batch_id=batch_id)
        if not ok:
            raise RuntimeError(message)
        runtime._step(request.job_id, cancel_flag, update, progress=90, message='批次已启动。')
        return {'batchId': batch_id, 'recipeId': recipe_id, 'message': message, 'started': True}


class ResetStationHandler(BaseActionHandler):
    kind = 'reset_station'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Pause the line, clear faults, and optionally resume automation."""
        app = runtime.context.app()
        resume_after = bool(request.payload.get('resumeAfter', False))
        runtime._step(request.job_id, cancel_flag, update, progress=20, message='下发暂停指令。')
        app.publish_control('pause')
        runtime._step(request.job_id, cancel_flag, update, progress=50, message='执行故障复位。', sleep_sec=0.01)
        ok, message = app.reset_fault()
        if not ok:
            raise RuntimeError(message)
        if resume_after:
            runtime._step(request.job_id, cancel_flag, update, progress=80, message='恢复自动运行。')
            app.publish_control('resume')
        return {'reset': True, 'resumeAfter': resume_after, 'message': message}


class RunCalibrationHandler(BaseActionHandler):
    kind = 'run_calibration'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Reject calibration execution until a real calibration workflow exists.

        Args:
            runtime: Shared action runtime services.
            request: Normalized action execution request.
            cancel_flag: Cooperative cancellation flag.
            update: Job-state publisher.

        Returns:
            No payload is returned because execution is blocked.

        Raises:
            ActionPolicyError: Always raised because the calibration workflow is
                intentionally not exposed as an executable path yet.

        Boundary behavior:
            The handler mirrors the catalog policy so accidental direct runtime
            invocation cannot silently recreate the previous stub behavior.
        """
        contract = action_contract(self.kind)
        raise ActionPolicyError(contract.kind, contract.capability.blocked_reason or 'calibration_workflow_not_available', contract.capability.summary or '标定闭环尚未落地，当前不可执行。')


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
        app.publish_control('pause')
        runtime._step(request.job_id, cancel_flag, update, progress=20, message='准备基准测试环境。', sleep_sec=0.01)
        app.publish_control('resume')
        runtime._step(request.job_id, cancel_flag, update, progress=70, message='执行基准采样。', sleep_sec=0.02)
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
        runtime._step(request.job_id, cancel_flag, update, progress=20, message='校验目标配方。')
        recipe = app.recipe_store.load_by_id(recipe_id)
        if not recipe:
            raise FileNotFoundError(f'recipe_not_found:{recipe_id}')
        dry_run = bool(request.payload.get('dryRun', False))
        if not dry_run:
            runtime._step(request.job_id, cancel_flag, update, progress=60, message='激活目标配方。')
            receipt = app.activate_recipe(recipe_id, operator=str(request.actor.get('username', 'anonymous')))
        else:
            receipt = {'recipeId': recipe_id, 'dryRun': True}
        runtime._step(request.job_id, cancel_flag, update, progress=90, message='写入配方切换结果。')
        return {'recipeId': recipe_id, 'dryRun': dry_run, 'validation': {'valid': True}, 'activation': receipt}


class StopStationHandler(BaseActionHandler):
    kind = 'stop_station'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Stop the station through the canonical control plane."""
        app = runtime.context.app()
        runtime._step(request.job_id, cancel_flag, update, progress=25, message='下发停线指令。')
        app.publish_control('stop')
        runtime._step(request.job_id, cancel_flag, update, progress=90, message='停线指令已提交。')
        return {'stopped': True, 'message': '已发布停止指令。'}


class SetMaintenanceModeHandler(BaseActionHandler):
    kind = 'set_maintenance_mode'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        """Request a maintenance-mode transition through the canonical action plane."""
        enabled = bool(request.payload.get('enabled', False))
        runtime._step(request.job_id, cancel_flag, update, progress=30, message='提交维护模式切换请求。')
        snapshot = runtime.context.app().request_maintenance_mode(enabled, actor=str(request.actor.get('username', 'anonymous')))
        runtime._step(request.job_id, cancel_flag, update, progress=90, message='维护模式请求已提交。')
        return snapshot


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
        runtime._step(request.job_id, cancel_flag, update, progress=20, message='校验维护态。')
        runtime._step(request.job_id, cancel_flag, update, progress=60, message='执行诊断动作。')
        result = app.run_diagnostic_action(self.diagnostic_action)
        runtime._step(request.job_id, cancel_flag, update, progress=90, message='诊断动作执行完成。')
        return result


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
        RunCalibrationHandler(),
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
