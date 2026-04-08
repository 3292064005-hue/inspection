from __future__ import annotations

import time
from typing import Any

from ...action_contract import ActionDispatchError
from ..context import GatewayAppContext
from ..service_common import app_facade

DIAGNOSTIC_ACTION_KIND_BY_NAME: dict[str, str] = {
    'CAPTURE_FRAME': 'diagnostic_capture_frame',
    'TEST_LIGHTING': 'diagnostic_test_lighting',
    'TEST_SORT_ACTUATOR': 'diagnostic_test_sort_actuator',
}
TERMINAL_ACTION_JOB_STATES = {'COMPLETED', 'FAILED', 'CANCELLED'}


class StationCommandService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def _default_start_payload(self) -> dict[str, Any]:
        state = getattr(app_facade(self.context), 'state', None)
        payload: dict[str, Any] = {}
        snapshot = state.snapshot_payload() if state is not None and hasattr(state, 'snapshot_payload') else {}
        recipe_id = str(getattr(state, 'active_recipe_id', '') or snapshot.get('activeRecipeId', '') or '').strip() if state is not None else ''
        batch_id = str(getattr(state, 'pending_batch_id', '') or getattr(state, 'batch_id', '') or snapshot.get('pendingBatchId', '') or snapshot.get('batchId', '') or '').strip() if state is not None else ''
        payload['recipeId'] = recipe_id or 'default_recipe'
        if batch_id:
            payload['batchId'] = batch_id
        return payload

    def _await_terminal_job(self, job_id: str, *, timeout_sec: float = 5.0, poll_interval_sec: float = 0.02) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.1, float(timeout_sec))
        last_job: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            job = self.context.action_job_service().get_job(job_id)
            if job is None:
                raise RuntimeError('station_action_job_missing')
            last_job = job
            status = str(job.get('status', '')).upper()
            if status in TERMINAL_ACTION_JOB_STATES:
                if status == 'COMPLETED':
                    return job
                error = job.get('error') if isinstance(job.get('error'), dict) else {}
                message = str(error.get('message') or error.get('detail') or job.get('message') or '工位动作执行失败。')
                raise RuntimeError(message)
            time.sleep(max(0.01, float(poll_interval_sec)))
        status = str((last_job or {}).get('status', 'PENDING')).upper()
        raise RuntimeError(f'station_action_job_timeout:{status}')

    def _submit_station_action(self, kind: str, payload: dict[str, Any], *, actor: dict[str, Any], action_name: str, resource: str, result_mapper: Any) -> dict[str, Any]:
        """Submit a legacy façade request through the persisted action plane only.

        Args:
            kind: Canonical action kind to submit.
            payload: Decoded action payload.
            actor: Authenticated actor metadata.
            action_name: Audit action name for the façade route.
            resource: Audit resource path.
            result_mapper: Callable mapping the terminal action job payload into
                the façade response schema.

        Returns:
            Legacy-compatible response payload derived from the terminal job.

        Raises:
            ActionDispatchError: When the canonical action plane is unavailable.
            Exception: Propagates validation, policy, and runtime job failures.

        Boundary behavior:
            Compatibility façades are no longer allowed to bypass the persisted
            action plane with direct control calls. They either submit through
            the canonical job surface or fail closed with a structured transport
            error so operators never observe divergent control semantics.
        """
        action_job_service_getter = getattr(self.context, 'action_job_service', None)
        if not callable(action_job_service_getter):
            raise ActionDispatchError(kind, 'action_plane_unavailable', '兼容控制面当前无法接入统一动作平面。', transport='compatibility_facade')
        try:
            action_job_service = action_job_service_getter()
            job = action_job_service.submit(kind, payload=payload, actor=actor)
        except ActionDispatchError:
            raise
        except Exception as exc:
            if isinstance(exc, (AttributeError, NotImplementedError, RuntimeError)):
                raise ActionDispatchError(kind, 'action_plane_unavailable', '兼容控制面当前无法接入统一动作平面。', transport='compatibility_facade') from exc
            raise
        job_id = str(job.get('jobId', ''))
        if not job_id:
            raise RuntimeError('station_action_job_submit_failed')
        terminal = self._await_terminal_job(job_id)
        result = terminal.get('result') if isinstance(terminal.get('result'), dict) else {}
        mapped = result_mapper(terminal, result)
        self.context.audit(
            actor=str(actor.get('username', 'anonymous')),
            role=str(actor.get('role', 'viewer')),
            action=action_name,
            resource=resource,
            result='SUCCESS',
            details={'jobId': job_id, 'kind': kind, 'payload': payload, 'result': mapped, 'transport': 'legacy_wrapper_over_action_plane'},
        )
        return mapped

    def start(self, *, actor: dict[str, Any]) -> dict[str, Any]:
        return self._submit_station_action('start_batch', self._default_start_payload(), actor=actor, action_name='STATION_START', resource='/station', result_mapper=lambda _job, result: {'success': bool(result.get('started', True)), 'message': str(result.get('message', '启动请求已提交。'))})

    def stop(self, *, actor: dict[str, Any]) -> dict[str, Any]:
        return self._submit_station_action('stop_station', {}, actor=actor, action_name='STATION_STOP', resource='/station', result_mapper=lambda _job, result: {'success': bool(result.get('stopped', True)), 'message': str(result.get('message', '已发布停止指令。'))})

    def reset_fault(self, *, actor: dict[str, Any]) -> dict[str, Any]:
        return self._submit_station_action('reset_station', {}, actor=actor, action_name='FAULT_RESET', resource='/station/fault', result_mapper=lambda _job, result: {'success': bool(result.get('reset', True)), 'message': str(result.get('message', '故障复位请求已完成。'))})

    def new_batch(self, *, actor: dict[str, Any]) -> dict[str, Any]:
        return self._submit_station_action('create_batch', {}, actor=actor, action_name='BATCH_NEW', resource='/station/batch', result_mapper=lambda _job, result: {'batchId': str(result.get('batchId', ''))})

    def set_maintenance_mode(self, enabled: bool, *, actor: dict[str, Any]) -> dict[str, Any]:
        return self._submit_station_action('set_maintenance_mode', {'enabled': bool(enabled)}, actor=actor, action_name='MAINTENANCE_MODE_ENABLE' if enabled else 'MAINTENANCE_MODE_DISABLE', resource='/station/maintenance', result_mapper=lambda _job, result: dict(result) if isinstance(result, dict) else {})


class DiagnosticsCommandService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def _normalize_kind(self, action: str) -> tuple[str, str]:
        normalized_action = str(action or '').strip().upper()
        kind = DIAGNOSTIC_ACTION_KIND_BY_NAME.get(normalized_action, '')
        if not kind:
            raise ValueError(f'unsupported_diagnostic_action:{normalized_action}')
        return normalized_action, kind

    def _await_terminal_job(self, job_id: str, *, timeout_sec: float = 5.0, poll_interval_sec: float = 0.02) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.1, float(timeout_sec))
        last_job: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            job = self.context.action_job_service().get_job(job_id)
            if job is None:
                raise RuntimeError('diagnostic_action_job_missing')
            last_job = job
            status = str(job.get('status', '')).upper()
            if status in TERMINAL_ACTION_JOB_STATES:
                if status == 'COMPLETED':
                    result = job.get('result')
                    if isinstance(result, dict):
                        return result
                    raise RuntimeError('diagnostic_action_job_missing_result')
                error = job.get('error') if isinstance(job.get('error'), dict) else {}
                message = str(error.get('message') or error.get('detail') or job.get('message') or '诊断动作执行失败。')
                raise RuntimeError(message)
            time.sleep(max(0.01, float(poll_interval_sec)))
        status = str((last_job or {}).get('status', 'PENDING')).upper()
        raise RuntimeError(f'diagnostic_action_job_timeout:{status}')

    def run_action(self, action: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        normalized_action, kind = self._normalize_kind(action)
        job = self.context.action_job_service().submit(kind, payload={}, actor=actor)
        job_id = str(job.get('jobId', ''))
        if not job_id:
            raise RuntimeError('diagnostic_action_job_submit_failed')
        result = self._await_terminal_job(job_id)
        self.context.audit(actor=str(actor.get('username', 'anonymous')), role=str(actor.get('role', 'viewer')), action=f'DIAGNOSTIC_{normalized_action}', resource='/diagnostics/actions', result='SUCCESS' if result.get('success') else 'FAILED', details={'jobId': job_id, 'result': result, 'transport': 'legacy_wrapper_over_action_plane'})
        return result


class ActionCommandService:
    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def submit(self, kind: str, payload: dict[str, Any], *, actor: dict[str, Any]) -> dict[str, Any]:
        return self.context.action_job_service().submit(kind, payload=payload, actor=actor)

    def cancel(self, job_id: str, *, actor: dict[str, Any]) -> dict[str, Any]:
        return self.context.action_job_service().cancel(job_id, actor=actor)
