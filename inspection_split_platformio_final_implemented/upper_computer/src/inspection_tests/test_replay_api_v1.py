from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from inspection_hmi_gateway.server.auth import hash_password
from inspection_hmi_gateway.server.main import create_app
from inspection_utils.config import save_yaml

from test_gateway_api_v1 import _FakeRuntime


def _users_file(tmp_path: Path) -> Path:
    path = tmp_path / 'users.yaml'
    save_yaml(path, {
        'users': {
            'viewer': {'password_hash': hash_password('viewer123'), 'role': 'viewer', 'display_name': '查看员'},
        }
    })
    return path


def _auth_header(client: TestClient) -> dict[str, str]:
    response = client.post('/api/v1/auth/login', json={'username': 'viewer', 'password': 'viewer123'})
    assert response.status_code == 200
    token = response.cookies.get('inspection_session')
    assert token
    return {'Authorization': f'Bearer {token}'}


def _write_replay_fixture(root: Path) -> None:
    (root / 'results').mkdir(parents=True, exist_ok=True)
    (root / 'events').mkdir(parents=True, exist_ok=True)
    (root / 'traces').mkdir(parents=True, exist_ok=True)
    (root / 'images').mkdir(parents=True, exist_ok=True)
    (root / 'images' / 'raw.png').write_bytes(b'raw-image')
    (root / 'images' / 'ann.png').write_bytes(b'annotated-image')
    with (root / 'results' / 'result_log.csv').open('w', encoding='utf-8', newline='') as fh:
        import csv
        writer = csv.writer(fh)
        writer.writerow(['time', 'trace_id', 'batch_id', 'item_id', 'recipe_id', 'category', 'defect_type', 'score', 'qr_ok', 'qr_text', 'orientation_ok', 'color_name', 'color_ratio', 'image_path', 'annotated_image_path', 'detail_json'])
        writer.writerow(['2026-03-31T08:00:00Z', 'trace-api', 'BATCH-API', 1, 'recipe-api', 'COLOR', 'SHIFT', 0.81, True, 'QR100', True, 'red', 0.8, 'images/raw.png', 'images/ann.png', json.dumps({'warnings': ['偏色'], 'processing_ms': 18.2}, ensure_ascii=False)])
    with (root / 'results' / 'cycle_summary.jsonl').open('w', encoding='utf-8') as fh:
        fh.write(json.dumps({'trace_id': 'trace-api', 'decision': 'NG', 'cycle_time_sec': 0.3}, ensure_ascii=False) + '\n')
    (root / 'traces' / 'trace-api.jsonl').write_text(json.dumps({'type': 'cycle_finish', 'trace_id': 'trace-api'}, ensure_ascii=False) + '\n', encoding='utf-8')
    with (root / 'results' / 'replay_manifest.jsonl').open('w', encoding='utf-8') as fh:
        fh.write(json.dumps({'trace_id': 'trace-api', 'trace_path': str(root / 'traces' / 'trace-api.jsonl'), 'summary': {'trace_id': 'trace-api'}, 'run_artifacts': {'bag_recording': {'enabled': False}}}, ensure_ascii=False) + '\n')


def test_replay_endpoints_list_and_fetch_trace(tmp_path: Path) -> None:
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_replay_fixture(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _FakeRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        headers = _auth_header(client)
        listed = client.get('/api/v1/replay/traces', headers=headers)
        assert listed.status_code == 200
        assert listed.json()['data'][0]['traceId'] == 'trace-api'
        assert listed.json()['data'][0]['artifactCount'] >= 1
        detail = client.get('/api/v1/replay/traces/trace-api', headers=headers)
        assert detail.status_code == 200
        assert detail.json()['data']['traceId'] == 'trace-api'
        assert detail.json()['data']['artifactCount'] >= 1
        compare = client.get('/api/v1/replay/traces/trace-api/compare', headers=headers)
        assert compare.status_code == 200
        assert compare.json()['data']['traceId'] == 'trace-api'
