from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol


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


class BaseActionHandler:
    kind: str = ''

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        raise NotImplementedError


class StartBatchHandler(BaseActionHandler):
    kind = 'start_batch'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
        app = runtime.context.app()
        batch_id = str(request.payload.get('batchId', '')).strip()
        runtime._step(request.job_id, cancel_flag, update, progress=15, message='准备批次上下文。')
        if not batch_id:
            batch_id = str(app.new_batch())
        runtime._step(request.job_id, cancel_flag, update, progress=55, message='下发启动请求。')
        ok, message = app.call_start()
        if not ok:
            raise RuntimeError(message)
        runtime._step(request.job_id, cancel_flag, update, progress=90, message='批次已启动。')
        return {'batchId': batch_id, 'message': message, 'started': True}


class ResetStationHandler(BaseActionHandler):
    kind = 'reset_station'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
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
        app = runtime.context.app()
        profile = str(request.payload.get('profile', 'default'))
        steps = [
            (20, '冻结当前工位。', 'pause'),
            (45, '触发标定采样。', 'manual_step_capture'),
            (70, '写入标定报告。', ''),
            (90, '恢复工位运行。', 'resume'),
        ]
        for progress, message, action in steps:
            runtime._step(request.job_id, cancel_flag, update, progress=progress, message=message, sleep_sec=0.01)
            if action:
                app.publish_control(action)
        report_path = runtime._write_job_report(request.job_id, 'calibration', {'profile': profile, 'completedAt': runtime.utc_now(), 'notes': ['calibration_stub_runtime']})
        return {'profile': profile, 'reportUrl': runtime._artifact_url(report_path), 'calibrated': True}


class ExecuteReplayHandler(BaseActionHandler):
    kind = 'execute_replay'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
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
        app = runtime.context.app()
        try:
            samples = max(1, int(request.payload.get('sampleCount', 10) or 10))
        except (TypeError, ValueError):
            samples = 10
        app.publish_control('pause')
        runtime._step(request.job_id, cancel_flag, update, progress=20, message='准备基准测试环境。', sleep_sec=0.01)
        app.publish_control('resume')
        runtime._step(request.job_id, cancel_flag, update, progress=70, message='执行基准采样。', sleep_sec=0.02)
        report_path = runtime._write_job_report(request.job_id, 'benchmark', {'sampleCount': samples, 'completedAt': runtime.utc_now(), 'mode': 'synthetic'})
        return {'sampleCount': samples, 'reportUrl': runtime._artifact_url(report_path), 'benchmarkCompleted': True}


class SwitchRecipeWithValidationHandler(BaseActionHandler):
    kind = 'switch_recipe_with_validation'

    def run(self, runtime: RuntimeSupport, request: ActionExecutionRequest, cancel_flag: Any, update: UpdateFn) -> dict[str, Any]:
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


ACTION_HANDLER_REGISTRY: dict[str, BaseActionHandler] = {
    handler.kind: handler for handler in (
        StartBatchHandler(),
        ResetStationHandler(),
        RunCalibrationHandler(),
        ExecuteReplayHandler(),
        ExportBatchHandler(),
        RunBenchmarkHandler(),
        SwitchRecipeWithValidationHandler(),
    )
}
