from __future__ import annotations

import os
import uuid
from typing import Any

from .action_contract import ACTION_CONTRACTS, action_contract, validate_action_payload
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

    def __init__(self, context: Any, *, max_workers: int = 4) -> None:
        self.context = context
        self.local_runtime = ActionExecutionRuntime(context, max_workers=max_workers)

    def shutdown(self) -> None:
        self.local_runtime.shutdown()

    def submit(self, kind: str, *, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        normalized_kind = str(kind or '').strip().lower()
        if normalized_kind not in SUPPORTED_ACTION_KINDS:
            raise ValueError(f'unsupported_action_kind:{normalized_kind}')
        validation_error = validate_action_payload(normalized_kind, payload)
        if validation_error:
            raise ValueError(validation_error)
        contract = action_contract(normalized_kind)
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
        }
        self.context.metadata_repository.record_action_job(record)
        self._broadcast(record)
        transport = 'local_runtime'
        if self._prefer_native_action_client() and self._dispatch_to_native_action(record, actor):
            transport = 'native_action'
        elif self._prefer_executor() and self._dispatch_to_executor(record, actor):
            transport = 'executor_bridge'
        else:
            if self._prefer_native_action_client() or self._prefer_executor():
                self._audit_transport_degradation('ACTION_JOB_TRANSPORT_FALLBACK', job_id=job_id, kind=normalized_kind, requested_native=self._prefer_native_action_client(), requested_executor=self._prefer_executor())
            self.local_runtime.submit(job_id, normalized_kind, payload=dict(payload), actor=dict(actor), update=self._update)
        record['transport'] = transport
        self.context.metadata_repository.record_action_job({'jobId': job_id, 'transport': transport})
        self.context.audit(
            actor=str(actor.get('username', 'anonymous')),
            role=str(actor.get('role', 'viewer')),
            action='ACTION_JOB_SUBMIT',
            resource=f'/actions/{normalized_kind}',
            details={'jobId': job_id, 'kind': normalized_kind, 'payload': payload},
        )
        return self.context.metadata_repository.get_action_job(job_id) or record

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

    def handle_executor_update(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict) or not str(payload.get('jobId', '')).strip():
            return
        self.context.metadata_repository.record_action_job(payload)
        merged = self.context.metadata_repository.get_action_job(str(payload.get('jobId', ''))) or dict(payload)
        self._maybe_record_export_job(merged)
        self._broadcast(merged)


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
