from __future__ import annotations

import os
import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from .action_contract import ACTION_CONTRACTS, ActionDispatchError, ActionPolicyError, action_contract, ensure_action_submit_allowed, validate_action_payload
from .diagnostic_action_policy import DiagnosticActionPolicy, load_diagnostic_action_policy
from .action_execution_runtime import ActionExecutionRuntime
from .server.responses import utc_now

SUPPORTED_ACTION_KINDS = set(ACTION_CONTRACTS)


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class ActionJobService:
    """Persisted action-job façade backed by a ROS executor node when available.

    The preferred path is now:
    HTTP/API -> persisted job record -> Gateway ROS transport -> independent
    ``inspection_action_executor_node`` -> job updates -> metadata repository.

    For unit tests or deployments where the executor node is unavailable, the
    previous in-process execution runtime remains as a compatibility fallback.
    """

    def __init__(self, context: Any, *, max_workers: int = 4, diagnostic_policy: DiagnosticActionPolicy | None = None) -> None:
        self.context = context
        self.local_runtime = ActionExecutionRuntime(context, max_workers=max_workers)
        self.diagnostic_policy = diagnostic_policy or load_diagnostic_action_policy()
        self._diagnostic_submit_lock = threading.Lock()

    def shutdown(self) -> None:
        self.local_runtime.shutdown()

    def submit(self, kind: str, *, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        """Create a persisted action job and dispatch it to the selected runtime.

        Args:
            kind: Action kind requested by the caller.
            payload: Already-decoded action payload.
            actor: Authenticated actor metadata used for audit logging.

        Returns:
            The persisted job record after transport selection has completed.

        Raises:
            ValueError: When the action kind or payload is invalid.
            PermissionError: When the action is catalogued but blocked by the
                current execution policy.

        Boundary behavior:
            Submission policy is enforced before any queued record is created so
            disabled or synthetic-only actions never masquerade as active jobs.
        """
        normalized_kind = str(kind or '').strip().lower()
        if normalized_kind not in SUPPORTED_ACTION_KINDS:
            raise ValueError(f'unsupported_action_kind:{normalized_kind}')
        validation_error = validate_action_payload(normalized_kind, payload)
        if validation_error:
            raise ValueError(validation_error)
        contract = ensure_action_submit_allowed(normalized_kind)
        job_id = f'{normalized_kind}-{uuid.uuid4().hex[:12]}'
        record = {
            'jobId': job_id,
            'kind': normalized_kind,
            'status': 'QUEUED',
            'progress': 0,
            'message': '任务已排队。',
            'createdAt': utc_now(),
            'startedAt': '',
            'completedAt': '',
            'requestedBy': str(actor.get('username', 'anonymous')),
            'requestedRole': str(actor.get('role', 'viewer')),
            'cancellable': True,
            'payload': dict(payload),
            'result': {},
            'error': {},
            'actionTopic': contract.topic,
            'actionType': contract.ros_type,
            'feedback': {'phase': 'QUEUED', 'progress': 0.0, 'detail': {'message': '任务已排队。'}},
            'capability': contract.capability.to_dict(),
        }
        self._persist_submission_record(record, actor=actor)
        transport = self._dispatch_submission(record, actor=actor)
        record['transport'] = transport
        self.context.metadata_repository.record_action_job({'jobId': job_id, 'transport': transport})
        persisted = self.context.metadata_repository.get_action_job(job_id) or record
        self._broadcast(persisted)
        self.context.audit(
            actor=str(actor.get('username', 'anonymous')),
            role=str(actor.get('role', 'viewer')),
            action='ACTION_JOB_SUBMIT',
            resource=f'/actions/{normalized_kind}',
            details={'jobId': job_id, 'kind': normalized_kind, 'payload': payload, 'transport': transport},
        )
        return persisted

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return self.context.metadata_repository.get_action_job(job_id)

    def list_jobs(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return self.context.metadata_repository.list_action_jobs(limit=limit, offset=offset)

    def cancel(self, job_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        current = self.context.metadata_repository.get_action_job(job_id)
        if current is None:
            raise ValueError('action_job_not_found')
        status = str(current.get('status', ''))
        if status in {'COMPLETED', 'FAILED', 'CANCELLED'}:
            return current
        if self._prefer_native_action_client() and self._cancel_via_native_action(job_id, actor):
            self._update(job_id, status='CANCELLING', progress=_safe_int(current.get('progress', 0), default=0), message='已请求通过原生 ROS Action 取消。')
        elif self._prefer_executor() and self._cancel_via_executor(job_id, actor):
            self._update(job_id, status='CANCELLING', progress=_safe_int(current.get('progress', 0), default=0), message='已请求取消，等待执行器响应。')
        else:
            if self._prefer_native_action_client() or self._prefer_executor():
                self._audit_transport_degradation('ACTION_JOB_CANCEL_FALLBACK', job_id=job_id, requested_native=self._prefer_native_action_client(), requested_executor=self._prefer_executor())
            _flag, future = self.local_runtime.cancel(job_id)
            if future is not None and future.cancel():
                self._update(job_id, status='CANCELLED', progress=_safe_int(current.get('progress', 0), default=0), message='任务已在执行前取消。', completedAt=utc_now())
            else:
                self._update(job_id, status='CANCELLING', progress=_safe_int(current.get('progress', 0), default=0), message='已请求取消，等待任务响应。')
        self.context.audit(
            actor=str(actor.get('username', 'anonymous')),
            role=str(actor.get('role', 'viewer')),
            action='ACTION_JOB_CANCEL',
            resource=f'/actions/jobs/{job_id}/cancel',
            details={'jobId': job_id},
        )
        return self.context.metadata_repository.get_action_job(job_id) or current

    def _dispatch_submission(self, record: dict[str, Any], *, actor: dict[str, Any]) -> str:
        """Submit a persisted action job to the selected execution transport.

        Args:
            record: Persisted action-job record prepared for dispatch.
            actor: Authenticated actor metadata for audit and bridge payloads.

        Returns:
            The accepted transport name.

        Raises:
            ActionDispatchError: When no execution transport can accept the job.

        Boundary behavior:
            If the final fallback transport rejects the submission synchronously,
            the already-persisted job is moved to FAILED immediately so callers
            never observe a permanent QUEUED zombie record.
        """
        job_id = str(record.get('jobId', ''))
        kind = str(record.get('kind', ''))
        if self._prefer_native_action_client() and self._dispatch_to_native_action(record, actor):
            return 'native_action'
        if self._prefer_executor() and self._dispatch_to_executor(record, actor):
            return 'executor_bridge'
        if self._prefer_native_action_client() or self._prefer_executor():
            self._audit_transport_degradation(
                'ACTION_JOB_TRANSPORT_FALLBACK',
                job_id=job_id,
                kind=kind,
                requested_native=self._prefer_native_action_client(),
                requested_executor=self._prefer_executor(),
            )
        try:
            self.local_runtime.submit(job_id, kind, payload=dict(record.get('payload', {})), actor=dict(actor), update=self._update)
        except Exception as exc:
            raise self._fail_submission_transport(record, actor=actor, transport='local_runtime', reason='action_transport_unavailable', message='动作提交失败，执行运行时当前不可用。', exc=exc) from exc
        return 'local_runtime'

    def _fail_submission_transport(
        self,
        record: dict[str, Any],
        *,
        actor: dict[str, Any],
        transport: str,
        reason: str,
        message: str,
        exc: Exception | None = None,
    ) -> ActionDispatchError:
        """Convert a synchronous transport failure into a terminal failed job.

        Args:
            record: Persisted action-job record that could not be dispatched.
            actor: Authenticated actor metadata for auditing.
            transport: Transport name that rejected the submission.
            reason: Machine-readable failure reason.
            message: Human-readable failure message.
            exc: Original synchronous exception from the transport layer.

        Returns:
            Structured dispatch error raised to HTTP callers.

        Boundary behavior:
            The failed record is marked terminal before the exception is raised so
            diagnostics in-flight guards do not see a phantom queued action.
        """
        job_id = str(record.get('jobId', ''))
        kind = str(record.get('kind', ''))
        detail = {
            'code': reason,
            'kind': kind,
            'message': message,
            'jobId': job_id,
            'transport': transport,
        }
        if exc is not None:
            detail['cause'] = str(exc)
        self._update(
            job_id,
            status='FAILED',
            progress=100,
            message=message,
            completedAt=utc_now(),
            error=detail,
            feedback={'phase': 'FAILED', 'progress': 1.0, 'detail': detail},
        )
        self.context.metadata_repository.record_action_job({'jobId': job_id, 'transport': transport})
        self._audit_transport_degradation('ACTION_JOB_SUBMIT_FAILED', job_id=job_id, kind=kind, transport=transport, reason=reason, actor=str(actor.get('username', 'anonymous')), error=str(exc) if exc is not None else '')
        return ActionDispatchError(kind, reason, message, job_id=job_id, transport=transport)

    def _persist_submission_record(self, record: dict[str, Any], *, actor: dict[str, Any]) -> None:
        """Persist a newly submitted action-job record.

        Args:
            record: Fully prepared action-job record ready for persistence.
            actor: Authenticated actor metadata used for rejection auditing.

        Returns:
            None.

        Raises:
            ActionPolicyError: When a diagnostics action is rejected by the
                committed maintenance/in-flight/cooldown policy.

        Boundary behavior:
            Hazardous diagnostics submissions are evaluated and recorded within a
            single process-level critical section so concurrent callers cannot
            pass the server-side policy check before the first queued record is
            persisted.
        """
        kind = str(record.get('kind', '')).strip().lower()
        if not self.diagnostic_policy.applies_to(kind):
            self.context.metadata_repository.record_action_job(record)
            return
        with self._diagnostic_submit_lock:
            try:
                self._enforce_diagnostic_submit_policy(kind)
                self.context.metadata_repository.record_action_job(record)
            except ActionPolicyError as exc:
                self._audit_submission_rejection(kind, actor=actor, payload=record.get('payload', {}), exc=exc)
                raise

    def _audit_submission_rejection(self, kind: str, *, actor: dict[str, Any], payload: Any, exc: ActionPolicyError) -> None:
        """Record rejected action submissions in the audit log.

        Args:
            kind: Canonical action kind requested by the caller.
            actor: Authenticated actor metadata.
            payload: Submitted payload preserved for traceability.
            exc: Policy rejection raised by the server-side guard.

        Returns:
            None.

        Raises:
            No exception is propagated from auditing; failures are swallowed so
            the original policy rejection remains authoritative.
        """
        try:
            self.context.audit(
                actor=str(actor.get('username', 'anonymous')),
                role=str(actor.get('role', 'viewer')),
                action='ACTION_JOB_SUBMIT_REJECTED',
                resource=f'/actions/{kind}',
                result='FAILED',
                details={
                    'kind': kind,
                    'reason': exc.reason,
                    'message': exc.user_message,
                    'payload': dict(payload) if isinstance(payload, dict) else {},
                },
            )
        except Exception:
            pass

    def handle_executor_update(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or not str(payload.get('jobId', '')).strip():
            return
        self.context.metadata_repository.record_action_job(payload)
        merged = self.context.metadata_repository.get_action_job(str(payload.get('jobId', ''))) or dict(payload)
        self._maybe_record_export_job(merged)
        self._broadcast(merged)


    def _enforce_diagnostic_submit_policy(self, kind: str) -> None:
        """Apply server-side guardrails for hazardous diagnostics actions.

        Args:
            kind: Canonical action kind requested by the caller.

        Returns:
            None.

        Raises:
            ActionPolicyError: When maintenance mode is not committed yet, when
                another hazardous diagnostics action is already running, or when
                the cooldown window is still active.

        Boundary behavior:
            The policy is evaluated before any persisted action-job record is
            created so rejected diagnostics submissions do not masquerade as
            queued jobs.
        """
        if not self.diagnostic_policy.applies_to(kind):
            return
        if self.diagnostic_policy.require_maintenance_enabled:
            maintenance = self._maintenance_snapshot()
            if not bool(maintenance.get('enabled', False)):
                transition_state = str(maintenance.get('transitionState', 'LOCKED')).upper()
                if transition_state == 'ENTERING':
                    raise ActionPolicyError(kind, 'diagnostic_requires_maintenance_confirmation', '维护模式请求已下发，但系统尚未确认进入手动态。')
                raise ActionPolicyError(kind, 'diagnostic_requires_maintenance_enabled', '维护模式未生效，危险动作已锁定。')

        recent_jobs, _total = self.context.action_job_repository.list(limit=200, offset=0)
        relevant_jobs = [job for job in recent_jobs if self.diagnostic_policy.applies_to(str(job.get('kind', '')))]
        blocking = next((job for job in relevant_jobs if str(job.get('status', '')).upper() not in {'COMPLETED', 'FAILED', 'CANCELLED'}), None)
        if blocking is not None:
            raise ActionPolicyError(kind, 'diagnostic_action_in_flight', '已有危险诊断动作正在执行，请等待当前动作结束。')

        if self.diagnostic_policy.cooldown_ms <= 0:
            return
        latest_same_kind = next((job for job in relevant_jobs if str(job.get('kind', '')).strip().lower() == kind and str(job.get('status', '')).upper() == 'COMPLETED'), None)
        if latest_same_kind is None:
            return
        completed_at = self._coerce_timestamp(latest_same_kind.get('completedAt')) or self._coerce_timestamp(latest_same_kind.get('createdAt'))
        if completed_at is None:
            return
        elapsed_ms = max(0, int((datetime.now(UTC) - completed_at).total_seconds() * 1000.0))
        if elapsed_ms >= int(self.diagnostic_policy.cooldown_ms):
            return
        remaining_sec = max(1, int(((int(self.diagnostic_policy.cooldown_ms) - elapsed_ms) + 999) / 1000))
        raise ActionPolicyError(kind, 'diagnostic_action_cooldown_active', f'诊断动作冷却中，请等待 {remaining_sec} 秒后重试。')

    def _maintenance_snapshot(self) -> dict[str, Any]:
        try:
            app = self.context.app()
        except Exception:
            return {'requested': False, 'enabled': False, 'transitionState': 'LOCKED'}
        snapshot = app.snapshot_payload() if hasattr(app, 'snapshot_payload') else {}
        maintenance = snapshot.get('maintenance', {}) if isinstance(snapshot, dict) else {}
        return maintenance if isinstance(maintenance, dict) else {'requested': False, 'enabled': False, 'transitionState': 'LOCKED'}

    def _coerce_timestamp(self, value: object) -> datetime | None:
        raw = str(value or '').strip()
        if not raw:
            return None
        try:
            normalized = raw.replace('Z', '+00:00') if raw.endswith('Z') else raw
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _prefer_executor(self) -> bool:
        return str(os.environ.get('INSPECTION_ACTION_EXECUTOR_ENABLED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}

    def _prefer_native_action_client(self) -> bool:
        return str(os.environ.get('INSPECTION_NATIVE_ACTION_CLIENT_ENABLED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}

    def _dispatch_to_native_action(self, record: dict[str, Any], actor: dict[str, Any]) -> bool:
        try:
            node = self.context.node()
        except Exception as exc:
            self._record_transport_failure('native_action', 'context.node_unavailable', exc=exc, job_id=str(record.get('jobId', '')), kind=str(record.get('kind', '')))
            return False
        if not hasattr(node, 'submit_native_action_goal'):
            self._record_transport_failure('native_action', 'submit_native_action_goal_missing', job_id=str(record.get('jobId', '')), kind=str(record.get('kind', '')))
            return False
        try:
            return bool(node.submit_native_action_goal(record, actor=actor, update=self._update))
        except Exception as exc:
            self._record_transport_failure('native_action', 'submit_native_action_goal_failed', exc=exc, job_id=str(record.get('jobId', '')), kind=str(record.get('kind', '')))
            return False

    def _cancel_via_native_action(self, job_id: str, actor: dict[str, Any]) -> bool:
        try:
            node = self.context.node()
        except Exception as exc:
            self._record_transport_failure('native_action', 'context.node_unavailable', exc=exc, job_id=job_id, operation='cancel')
            return False
        if not hasattr(node, 'cancel_native_action_goal'):
            self._record_transport_failure('native_action', 'cancel_native_action_goal_missing', job_id=job_id, operation='cancel')
            return False
        try:
            return bool(node.cancel_native_action_goal(job_id, actor))
        except Exception as exc:
            self._record_transport_failure('native_action', 'cancel_native_action_goal_failed', exc=exc, job_id=job_id, operation='cancel')
            return False

    def _dispatch_to_executor(self, record: dict[str, Any], actor: dict[str, Any]) -> bool:
        try:
            node = self.context.node()
        except Exception as exc:
            self._record_transport_failure('executor_bridge', 'context.node_unavailable', exc=exc, job_id=str(record.get('jobId', '')), kind=str(record.get('kind', '')))
            return False
        if not hasattr(node, 'submit_action_execution'):
            self._record_transport_failure('executor_bridge', 'submit_action_execution_missing', job_id=str(record.get('jobId', '')), kind=str(record.get('kind', '')))
            return False
        request = {
            'jobId': str(record.get('jobId', '')),
            'kind': str(record.get('kind', '')),
            'payload': dict(record.get('payload', {})),
            'actor': {'username': str(actor.get('username', 'anonymous')), 'role': str(actor.get('role', 'viewer'))},
            'actionTopic': str(record.get('actionTopic', '')),
            'actionType': str(record.get('actionType', '')),
        }
        try:
            return bool(node.submit_action_execution(request))
        except Exception as exc:
            self._record_transport_failure('executor_bridge', 'submit_action_execution_failed', exc=exc, job_id=str(record.get('jobId', '')), kind=str(record.get('kind', '')))
            return False

    def _cancel_via_executor(self, job_id: str, actor: dict[str, Any]) -> bool:
        try:
            node = self.context.node()
        except Exception as exc:
            self._record_transport_failure('executor_bridge', 'context.node_unavailable', exc=exc, job_id=job_id, operation='cancel')
            return False
        if not hasattr(node, 'cancel_action_execution'):
            self._record_transport_failure('executor_bridge', 'cancel_action_execution_missing', job_id=job_id, operation='cancel')
            return False
        try:
            return bool(node.cancel_action_execution(job_id, actor))
        except Exception as exc:
            self._record_transport_failure('executor_bridge', 'cancel_action_execution_failed', exc=exc, job_id=job_id, operation='cancel')
            return False

    def _record_transport_failure(self, transport: str, reason: str, *, exc: Exception | None = None, **details: Any) -> None:
        payload = {'transport': transport, 'reason': reason, **details}
        if exc is not None:
            payload['error'] = str(exc)
        self._audit_transport_degradation('ACTION_JOB_TRANSPORT_ERROR', **payload)

    def _audit_transport_degradation(self, action: str, **details: Any) -> None:
        try:
            self.context.audit(actor='system', role='system', action=action, resource='/actions/jobs', details=details)
        except Exception:
            pass

    def _maybe_record_export_job(self, payload: dict[str, Any]) -> None:
        if str(payload.get('kind', '')) != 'export_batch':
            return
        if str(payload.get('status', '')) != 'COMPLETED':
            return
        result = payload.get('result', {}) if isinstance(payload.get('result', {}), dict) else {}
        export_url = str(result.get('exportUrl', ''))
        if not export_url:
            return
        export_payload = {
            'jobId': str(result.get('jobId', f"export-{str(payload.get('jobId', ''))}")),
            'batchId': str(result.get('batchId', payload.get('payload', {}).get('batchId', ''))),
            'status': 'COMPLETED',
            'createdAt': str(result.get('createdAt', payload.get('createdAt', utc_now()))),
            'completedAt': str(result.get('completedAt', payload.get('completedAt', utc_now()))),
            'requestedBy': str(payload.get('requestedBy', 'anonymous')),
            'exportUrl': export_url,
            'itemCount': _safe_int(result.get('itemCount', 0), default=0),
            'traceCount': _safe_int(result.get('traceCount', 0), default=0),
            'details': {'filename': str(result.get('details', {}).get('filename', '')), 'sourceActionJobId': str(payload.get('jobId', ''))},
        }
        self.context.metadata_repository.record_export_job(export_payload)

    def _update(self, job_id: str, **fields: Any) -> None:
        self.context.metadata_repository.record_action_job({'jobId': job_id, **fields})
        payload = self.context.metadata_repository.get_action_job(job_id)
        if payload is not None:
            self._maybe_record_export_job(payload)
            self._broadcast(payload)

    def _broadcast(self, payload: dict[str, Any]) -> None:
        event_bus = getattr(self.context.runtime, 'event_bus', None)
        if event_bus is not None and hasattr(event_bus, 'broadcast'):
            try:
                event_bus.broadcast('action.job.updated', payload)
            except Exception:
                pass
