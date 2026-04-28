from __future__ import annotations

import json
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from inspection_utils.io_common import relative_artifact_path

from .action_contract import ActionPolicyError, ensure_action_submit_allowed
from .action_handlers import ACTION_HANDLER_REGISTRY, ActionExecutionRequest
from .server.responses import utc_now


class JobCancelled(Exception):
    pass


class ActionExecutionRuntime:
    """Independent execution kernel for long-running action jobs.

    The gateway job service persists and broadcasts state, while this runtime
    owns worker scheduling, cancellation, and delegates per-action execution to
    dedicated handler classes. This keeps native action servers, transport, and
    execution responsibilities separated.
    """

    def __init__(self, context: Any, *, max_workers: int = 4) -> None:
        self.context = context
        self.max_workers = max(1, int(max_workers))
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix='inspection-action-runtime')
        self._futures: dict[str, Future[Any]] = {}
        self._cancel_flags: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def shutdown(self) -> None:
        self.executor.shutdown(wait=False, cancel_futures=True)

    def submit(self, job_id: str, kind: str, *, payload: dict[str, Any], actor: dict[str, Any], update: Callable[..., None]) -> None:
        """Schedule an action job on the dedicated worker pool.

        Args:
            job_id: Persisted action-job identifier.
            kind: Normalized action kind.
            payload: Validated action payload.
            actor: Audit actor metadata.
            update: Callback used to persist and broadcast job state changes.

        Returns:
            None.

        Raises:
            No synchronous exception is raised once the worker is queued.

        Boundary behavior:
            Submission policy is enforced again inside the worker so direct
            runtime callers cannot bypass catalog-level execution guards.
        """
        cancel_flag = threading.Event()
        with self._lock:
            self._cancel_flags[job_id] = cancel_flag
            self._futures[job_id] = self.executor.submit(self._run_job, job_id, kind, dict(payload), dict(actor), cancel_flag, update)

    def cancel(self, job_id: str) -> tuple[threading.Event | None, Future[Any] | None]:
        with self._lock:
            flag = self._cancel_flags.get(job_id)
            future = self._futures.get(job_id)
        if flag is not None:
            flag.set()
        return flag, future

    def utc_now(self) -> str:
        return utc_now()

    def relative_artifact_path(self, path: str | Path) -> str:
        return relative_artifact_path(self.context.log_root, path)

    def _finalize(self, job_id: str) -> None:
        with self._lock:
            self._futures.pop(job_id, None)
            self._cancel_flags.pop(job_id, None)

    def _run_job(self, job_id: str, kind: str, payload: dict[str, Any], actor: dict[str, Any], cancel_flag: threading.Event, update: Callable[..., None]) -> None:
        try:
            update(job_id, status='RUNNING', startedAt=utc_now(), progress=5, message='任务开始执行。', feedback={'phase': 'RUNNING', 'progress': 0.05, 'detail': {'message': '任务开始执行。'}})
            request = ActionExecutionRequest(job_id=job_id, kind=kind, payload=dict(payload), actor=dict(actor))
            result = self._dispatch(request, cancel_flag, update)
            update(job_id, status='COMPLETED', progress=100, message='任务执行完成。', completedAt=utc_now(), result=result, feedback={'phase': 'COMPLETED', 'progress': 1.0, 'detail': {'result': result}})
            self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action='ACTION_JOB_COMPLETE', resource=f'/actions/{kind}', details={'jobId': job_id, 'kind': kind, 'result': result})
        except JobCancelled:
            update(job_id, status='CANCELLED', message='任务已取消。', completedAt=utc_now(), feedback={'phase': 'CANCELLED', 'progress': 1.0, 'detail': {'message': '任务已取消。'}})
        except ActionPolicyError as exc:
            update(
                job_id,
                status='FAILED',
                message='动作执行被策略拒绝。',
                completedAt=utc_now(),
                error=exc.to_payload(),
                feedback={'phase': 'FAILED', 'progress': 1.0, 'detail': exc.to_payload()},
            )
        except Exception as exc:
            update(job_id, status='FAILED', message='任务执行失败。', completedAt=utc_now(), error={'message': str(exc)}, feedback={'phase': 'FAILED', 'progress': 1.0, 'detail': {'message': str(exc)}})
        finally:
            self._finalize(job_id)

    def _dispatch(self, request: ActionExecutionRequest, cancel_flag: threading.Event, update: Callable[..., None]) -> dict[str, Any]:
        ensure_action_submit_allowed(request.kind)
        handler = ACTION_HANDLER_REGISTRY.get(str(request.kind or '').strip().lower())
        if handler is None:
            raise ValueError(f'unsupported_action_kind:{request.kind}')
        return handler.run(self, request, cancel_flag, update)

    def _check_cancel(self, cancel_flag: threading.Event) -> None:
        if cancel_flag.is_set():
            raise JobCancelled()

    def _step(self, job_id: str, cancel_flag: threading.Event, update: Callable[..., None], *, progress: int, message: str, sleep_sec: float = 0.0) -> None:
        self._check_cancel(cancel_flag)
        phase = str(message).split('。', 1)[0] or 'RUNNING'
        update(job_id, progress=progress, message=message, feedback={'phase': phase, 'progress': float(progress) / 100.0, 'detail': {'message': message}})
        if sleep_sec > 0:
            time.sleep(float(sleep_sec))
        self._check_cancel(cancel_flag)

    def _write_job_report(self, job_id: str, category: str, payload: dict[str, Any]) -> Path:
        report_root = Path(self.context.log_root) / 'action_jobs' / category
        report_root.mkdir(parents=True, exist_ok=True)
        path = report_root / f'{job_id}.json'
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        return path

    def _artifact_url(self, path: str | Path) -> str:
        return f"/artifacts/{relative_artifact_path(self.context.log_root, path)}"
