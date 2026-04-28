from __future__ import annotations

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from inspection_hmi_gateway.action_contract import ActionPolicyError
from inspection_hmi_gateway.server.main import create_app

from recipe_payloads import make_hmi_recipe_payload
from test_gateway_api_v1 import _FakeRuntime, _auth_header, _users_file, _write_logs


class _MaintenanceEnabledRuntime(_FakeRuntime):
    def __init__(self, logs_root: Path, recipes_root: Path) -> None:
        super().__init__(logs_root, recipes_root)

        original_snapshot = self.node.state.snapshot_payload

        def snapshot_payload() -> dict:
            payload = dict(original_snapshot())
            maintenance = dict(payload.get('maintenance', {}))
            maintenance.update({
                'requested': True,
                'enabled': True,
                'transitionState': 'ENABLED',
                'supervisorMode': 'MAINTENANCE',
                'source': 'test_fixture',
            })
            payload['maintenance'] = maintenance
            payload['supervisorMode'] = 'MAINTENANCE'
            return payload

        self.node.state.snapshot_payload = snapshot_payload


def _poll_job(client: TestClient, headers: dict[str, str], job_id: str, *, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    last: dict | None = None
    while time.time() < deadline:
        response = client.get(f'/api/v1/actions/jobs/{job_id}', headers=headers)
        assert response.status_code == 200
        last = response.json()['data']
        if last['status'] in {'COMPLETED', 'FAILED', 'CANCELLED'}:
            return last
        time.sleep(0.02)
    assert last is not None
    return last


def test_action_job_execute_replay_and_export_batch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '1')
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    # replay fixture
    (logs_root / 'results' / 'replay_manifest.jsonl').write_text('{"trace_id":"trace-api","trace_path":"' + str((logs_root / 'traces' / 'trace-api.jsonl').as_posix()) + '","summary":{"trace_id":"trace-api"},"run_artifacts":{}}\n', encoding='utf-8')
    (logs_root / 'traces' / 'trace-api.jsonl').write_text('{"type":"cycle_finish","trace_id":"trace-api"}\n', encoding='utf-8')
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _FakeRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        operator_headers = _auth_header(client, 'operator', 'operator123')
        replay_submit = client.post('/api/v1/actions/execute-replay', headers=operator_headers, json={'traceId': 'trace-api'})
        assert replay_submit.status_code == 200
        replay_job = _poll_job(client, operator_headers, replay_submit.json()['data']['jobId'])
        assert replay_job['status'] == 'COMPLETED'
        assert replay_job['result']['traceId'] == 'trace-api'
        assert replay_job['result']['reportUrl'].startswith('/artifacts/action_jobs/replay/')

        export_submit = client.post('/api/v1/actions/export-batch', headers=operator_headers, json={'batchId': 'BATCH-API'})
        assert export_submit.status_code == 200
        export_job = _poll_job(client, operator_headers, export_submit.json()['data']['jobId'])
        assert export_job['status'] == 'COMPLETED'
        assert export_job['result']['batchId'] == 'BATCH-API'
        assert export_job['result']['exportUrl'].startswith('/artifacts/exports/')

        listed = client.get('/api/v1/actions/jobs?limit=10&offset=0', headers=operator_headers)
        assert listed.status_code == 200
        assert listed.json()['meta']['page']['total'] >= 2


def test_action_job_switch_recipe_and_cancel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '1')
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _FakeRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        admin_headers = _auth_header(client, 'admin', 'admin123')
        operator_headers = _auth_header(client, 'operator', 'operator123')
        # seed extra recipe
        recipe_resp = client.post('/api/v1/recipes', headers=admin_headers, json=make_hmi_recipe_payload(recipe_id='recipe-next', name='下一配方', version='1.0.1'))
        assert recipe_resp.status_code == 200

        switch_submit = client.post('/api/v1/actions/switch-recipe', headers=admin_headers, json={'recipeId': 'recipe-next'})
        assert switch_submit.status_code == 200
        switch_job = _poll_job(client, admin_headers, switch_submit.json()['data']['jobId'])
        assert switch_job['status'] == 'COMPLETED'
        assert switch_job['result']['recipeId'] == 'recipe-next'

        calibration_submit = client.post('/api/internal/actions/run-calibration', headers=operator_headers, json={'profile': 'camera-main'})
        assert calibration_submit.status_code == 404

        blocked_submit = client.post('/api/internal/actions/run-calibration', headers=admin_headers, json={'profile': 'camera-main'})
        assert blocked_submit.status_code == 404


def test_action_job_submit_rejects_missing_required_payload(tmp_path: Path, monkeypatch) -> None:
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _FakeRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        operator_headers = _auth_header(client, 'operator', 'operator123')
        missing_recipe = client.post('/api/v1/actions/start-batch', headers=operator_headers, json={'batchId': 'BATCH-1'})
        assert missing_recipe.status_code == 422
        assert missing_recipe.json()['error']['code'] == 'VALIDATION_ERROR'

        missing_trace = client.post('/api/v1/actions/execute-replay', headers=operator_headers, json={'traceId': ''})
        assert missing_trace.status_code == 422
        assert missing_trace.json()['error']['code'] == 'VALIDATION_ERROR'


def test_run_benchmark_is_available_as_internal_synthetic_tooling_action(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '1')
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _FakeRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        admin_headers = _auth_header(client, 'admin', 'admin123')
        submit = client.post('/api/internal/actions/run-benchmark', headers=admin_headers, json={'sampleCount': 3})
        assert submit.status_code == 200
        job = _poll_job(client, admin_headers, submit.json()['data']['jobId'])
        assert job['status'] == 'COMPLETED'
        assert job['result']['executionClass'] == 'synthetic'
        assert job['kind'] == 'run_benchmark'


def test_action_job_diagnostics_submit_via_standard_action_plane(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '1')
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _MaintenanceEnabledRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        admin_headers = _auth_header(client, 'admin', 'admin123')
        submit = client.post('/api/v1/actions/diagnostics/capture-frame', headers=admin_headers, json={})
        assert submit.status_code == 200
        job = _poll_job(client, admin_headers, submit.json()['data']['jobId'])
        assert job['status'] == 'COMPLETED'
        assert job['kind'] == 'diagnostic_capture_frame'
        assert job['result']['action'] == 'CAPTURE_FRAME'
        assert job['result']['success'] is True


def test_action_job_diagnostics_require_committed_maintenance_mode(tmp_path: Path) -> None:
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _FakeRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        admin_headers = _auth_header(client, 'admin', 'admin123')
        blocked = client.post('/api/v1/actions/diagnostics/capture-frame', headers=admin_headers, json={})
        assert blocked.status_code == 409
        assert blocked.json()['message'] == '维护模式未生效，危险动作已锁定。'
        assert blocked.json()['error']['detail']['code'] == 'diagnostic_requires_maintenance_enabled'


def test_action_job_diagnostics_server_side_cooldown_blocks_duplicate_submit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '1')
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _MaintenanceEnabledRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        admin_headers = _auth_header(client, 'admin', 'admin123')
        first = client.post('/api/v1/actions/diagnostics/capture-frame', headers=admin_headers, json={})
        assert first.status_code == 200
        first_job = _poll_job(client, admin_headers, first.json()['data']['jobId'])
        assert first_job['status'] == 'COMPLETED'
        duplicate = client.post('/api/v1/actions/diagnostics/capture-frame', headers=admin_headers, json={})
        assert duplicate.status_code == 409
        assert duplicate.json()['message'].startswith('诊断动作冷却中，请等待 ')
        assert duplicate.json()['error']['detail']['code'] == 'diagnostic_action_cooldown_active'


def test_action_job_diagnostics_concurrent_submit_is_serialized_server_side(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '1')
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _MaintenanceEnabledRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        service = client.app.state.gateway_context.action_job_service()
        service.local_runtime.submit = lambda *args, **kwargs: None
        actor = {'username': 'admin', 'role': 'admin'}
        barrier = threading.Barrier(2)
        outcomes: list[tuple[str, str]] = []

        def worker() -> None:
            try:
                barrier.wait(timeout=2.0)
                job = service.submit('diagnostic_capture_frame', payload={}, actor=actor)
                outcomes.append(('ok', str(job.get('jobId', ''))))
            except ActionPolicyError as exc:
                outcomes.append(('blocked', exc.reason))

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2.0)

        assert sorted(kind for kind, _value in outcomes) == ['blocked', 'ok']
        assert any(value == 'diagnostic_action_in_flight' for kind, value in outcomes if kind == 'blocked')
        listed = client.get('/api/v1/actions/jobs?limit=20&offset=0', headers=_auth_header(client, 'admin', 'admin123'))
        assert listed.status_code == 200
        capture_jobs = [item for item in listed.json()['data'] if item['kind'] == 'diagnostic_capture_frame']
        assert len(capture_jobs) == 1


def test_action_job_diagnostics_rejection_is_audited_and_returns_human_message(tmp_path: Path) -> None:
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _FakeRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        admin_headers = _auth_header(client, 'admin', 'admin123')
        blocked = client.post('/api/v1/actions/diagnostics/capture-frame', headers=admin_headers, json={})
        assert blocked.status_code == 409
        payload = blocked.json()
        assert payload['message'] == '维护模式未生效，危险动作已锁定。'
        assert payload['error']['detail']['code'] == 'diagnostic_requires_maintenance_enabled'
        assert payload['error']['detail']['message'] == '维护模式未生效，危险动作已锁定。'

        audit_response = client.get('/api/v1/audit?limit=20&offset=0', headers=admin_headers)
        assert audit_response.status_code == 200
        audit_entries = audit_response.json()['data']
        rejection = next(item for item in audit_entries if item['action'] == 'ACTION_JOB_SUBMIT_REJECTED')
        assert rejection['result'] == 'FAILED'
        assert rejection['details']['reason'] == 'diagnostic_requires_maintenance_enabled'
        assert rejection['details']['message'] == '维护模式未生效，危险动作已锁定。'


def test_action_job_transport_failure_marks_job_failed_and_does_not_block_future_diagnostics(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '1')
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _MaintenanceEnabledRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        admin_headers = _auth_header(client, 'admin', 'admin123')
        service = client.app.state.gateway_context.action_job_service()
        original_submit = service.local_runtime.submit
        call_count = {'count': 0}

        def flaky_submit(*args, **kwargs):
            call_count['count'] += 1
            if call_count['count'] == 1:
                raise RuntimeError('executor unavailable for test')
            return original_submit(*args, **kwargs)

        service.local_runtime.submit = flaky_submit

        first = client.post('/api/v1/actions/diagnostics/capture-frame', headers=admin_headers, json={})
        assert first.status_code == 503
        first_payload = first.json()
        assert first_payload['message'] == '动作提交失败，执行运行时当前不可用。'
        assert first_payload['error']['detail']['code'] == 'action_transport_unavailable'
        failed_job_id = first_payload['error']['detail']['jobId']

        failed_job_response = client.get(f'/api/v1/actions/jobs/{failed_job_id}', headers=admin_headers)
        assert failed_job_response.status_code == 200
        failed_job = failed_job_response.json()['data']
        assert failed_job['status'] == 'FAILED'
        assert failed_job['error']['code'] == 'action_transport_unavailable'

        second = client.post('/api/v1/actions/diagnostics/capture-frame', headers=admin_headers, json={})
        assert second.status_code == 200
        second_job = _poll_job(client, admin_headers, second.json()['data']['jobId'])
        assert second_job['status'] == 'COMPLETED'

        audit_response = client.get('/api/v1/audit?limit=50&offset=0', headers=admin_headers)
        assert audit_response.status_code == 200
        audit_entries = audit_response.json()['data']
        failure_entry = next(item for item in audit_entries if item['action'] == 'ACTION_JOB_SUBMIT_FAILED')
        assert failure_entry['details']['reason'] == 'action_transport_unavailable'
        assert failure_entry['details']['transport'] == 'local_runtime'
