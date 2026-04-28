from __future__ import annotations

from pathlib import Path

from inspection_hmi_gateway.action_job_service import ActionJobService


class _Metadata:
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.exports: list[dict] = []

    def record_action_job(self, payload: dict) -> None:
        existing = dict(self.jobs.get(str(payload.get('jobId', '')), {}))
        existing.update(payload)
        self.jobs[str(existing.get('jobId', ''))] = existing

    def get_action_job(self, job_id: str):
        payload = self.jobs.get(job_id)
        return None if payload is None else dict(payload)

    def list_action_jobs(self, *, limit: int = 100, offset: int = 0):
        items = list(self.jobs.values())[offset:offset + limit]
        return [dict(item) for item in items], len(self.jobs)

    def record_export_job(self, payload: dict) -> None:
        self.exports.append(dict(payload))


class _Node:
    def __init__(self):
        self.submitted: list[dict] = []
        self.cancelled: list[tuple[str, dict]] = []
        self.handlers = []

    def submit_action_execution(self, payload: dict) -> bool:
        self.submitted.append(dict(payload))
        return True

    def cancel_action_execution(self, job_id: str, actor: dict) -> bool:
        self.cancelled.append((job_id, dict(actor)))
        return True

    def register_action_executor_updates(self, handler):
        self.handlers.append(handler)


class _Runtime:
    def __init__(self):
        self.event_bus = None


class _Context:
    def __init__(self, root: Path):
        self.log_root = root
        self.metadata_repository = _Metadata()
        self.runtime = _Runtime()
        self._node = _Node()
        self.audits = []

    def node(self):
        return self._node

    def audit(self, **payload):
        self.audits.append(payload)


def test_action_job_service_dispatches_via_executor_transport(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_EXECUTOR_ENABLED', 'true')
    context = _Context(tmp_path)
    service = ActionJobService(context)

    job = service.submit('export_batch', payload={'batchId': 'B-1'}, actor={'username': 'operator', 'role': 'operator'})
    assert job['kind'] == 'export_batch'
    assert context._node.submitted
    submitted = context._node.submitted[0]
    assert submitted['jobId'] == job['jobId']
    assert submitted['kind'] == 'export_batch'

    service.handle_executor_update(
        {
            'jobId': job['jobId'],
            'kind': 'export_batch',
            'status': 'COMPLETED',
            'requestedBy': 'operator',
            'result': {
                'jobId': 'export-1',
                'batchId': 'B-1',
                'exportUrl': '/artifacts/exports/B-1.zip',
                'itemCount': 2,
                'traceCount': 2,
                'details': {'filename': 'B-1.zip'},
            },
        }
    )
    assert context.metadata_repository.exports
    assert context.metadata_repository.exports[0]['batchId'] == 'B-1'


def test_action_job_service_cancels_via_executor_transport(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_EXECUTOR_ENABLED', 'true')
    context = _Context(tmp_path)
    service = ActionJobService(context)
    job = service.submit('export_batch', payload={'batchId': 'B-2'}, actor={'username': 'operator', 'role': 'operator'})
    cancelled = service.cancel(job['jobId'], actor={'username': 'operator', 'role': 'operator'})
    assert cancelled['status'] == 'CANCELLING'
    assert context._node.cancelled == [(job['jobId'], {'username': 'operator', 'role': 'operator'})]


class _FailingNode:
    def submit_action_execution(self, _payload: dict) -> bool:
        raise RuntimeError('executor down')


class _NativeMissingNode:
    pass


def test_action_job_service_audits_executor_transport_errors(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_EXECUTOR_ENABLED', 'true')
    monkeypatch.delenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', raising=False)
    context = _Context(tmp_path)
    context._node = _FailingNode()
    service = ActionJobService(context)
    try:
        service.submit('export_batch', payload={'batchId': 'B-3'}, actor={'username': 'operator', 'role': 'operator'})
    except RuntimeError as exc:
        assert '统一动作执行链路当前不可用' in str(exc)
    else:
        raise AssertionError('submit should fail closed when no canonical transport is available')
    failed_jobs, _total = context.metadata_repository.list_action_jobs(limit=10, offset=0)
    assert failed_jobs and failed_jobs[0]['status'] == 'FAILED'
    assert any(audit.get('action') == 'ACTION_JOB_TRANSPORT_ERROR' for audit in context.audits)
    detail = next(audit['details'] for audit in context.audits if audit.get('action') == 'ACTION_JOB_TRANSPORT_ERROR')
    assert detail['transport'] == 'executor_bridge'
    assert detail['reason'] == 'submit_action_execution_failed'


def test_action_job_service_audits_missing_native_action_transport(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('INSPECTION_NATIVE_ACTION_CLIENT_ENABLED', 'true')
    monkeypatch.delenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', raising=False)
    context = _Context(tmp_path)
    context._node = _NativeMissingNode()
    service = ActionJobService(context)
    try:
        service.submit('export_batch', payload={'batchId': 'B-4'}, actor={'username': 'operator', 'role': 'operator'})
    except RuntimeError as exc:
        assert '统一动作执行链路当前不可用' in str(exc)
    else:
        raise AssertionError('submit should fail closed when native action transport is unavailable')
    detail = next(audit['details'] for audit in context.audits if audit.get('action') == 'ACTION_JOB_TRANSPORT_ERROR')
    assert detail['transport'] == 'native_action'
    assert detail['reason'] == 'submit_native_action_goal_missing'



def test_action_job_service_rejects_removed_calibration_submit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '1')
    context = _Context(tmp_path)
    service = ActionJobService(context)
    try:
        service.submit('run_calibration', payload={'profile': 'main'}, actor={'username': 'maintainer', 'role': 'maintainer'})
    except ValueError as exc:
        assert 'unsupported_action_kind:run_calibration' in str(exc)
    else:  # pragma: no cover - regression guard
        raise AssertionError('run_calibration submit should be rejected because the action was removed')


def test_action_job_service_catalog_payload_contains_capability(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '1')
    context = _Context(tmp_path)
    service = ActionJobService(context)
    job = service.submit('export_batch', payload={'batchId': 'B-5'}, actor={'username': 'operator', 'role': 'operator'})
    assert job['capability']['availability'] == 'production_ready'
