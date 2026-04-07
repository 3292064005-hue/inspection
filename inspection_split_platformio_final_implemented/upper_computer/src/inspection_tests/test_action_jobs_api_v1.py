from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from inspection_hmi_gateway.server.main import create_app

from test_gateway_api_v1 import _FakeRuntime, _auth_header, _users_file, _write_logs


def _poll_job(client: TestClient, headers: dict[str, str], job_id: str, *, timeout: float = 2.0) -> dict:
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


def test_action_job_execute_replay_and_export_batch(tmp_path: Path) -> None:
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


def test_action_job_switch_recipe_and_cancel(tmp_path: Path) -> None:
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
        recipe_resp = client.post('/api/v1/recipes', headers=admin_headers, json={'id': 'recipe-next', 'name': '下一配方', 'version': '1.0.1', 'roi': [1, 2, 3, 4], 'qrRoi': [5, 6, 7, 8]})
        assert recipe_resp.status_code == 200

        switch_submit = client.post('/api/v1/actions/switch-recipe', headers=admin_headers, json={'recipeId': 'recipe-next'})
        assert switch_submit.status_code == 200
        switch_job = _poll_job(client, admin_headers, switch_submit.json()['data']['jobId'])
        assert switch_job['status'] == 'COMPLETED'
        assert switch_job['result']['recipeId'] == 'recipe-next'

        calibration_submit = client.post('/api/v1/actions/run-calibration', headers=operator_headers, json={'profile': 'camera-main'})
        # operator lacks maintainer role
        assert calibration_submit.status_code == 403



def test_action_job_submit_rejects_missing_required_payload(tmp_path: Path) -> None:
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
        assert missing_recipe.status_code == 400
        assert missing_recipe.json()['error']['code'] == 'HTTP_400'

        missing_trace = client.post('/api/v1/actions/execute-replay', headers=operator_headers, json={'traceId': ''})
        assert missing_trace.status_code == 400
        assert missing_trace.json()['error']['code'] == 'HTTP_400'
