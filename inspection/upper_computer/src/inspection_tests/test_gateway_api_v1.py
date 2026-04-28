from __future__ import annotations

import csv
import json

import pytest
from pathlib import Path

from fastapi.testclient import TestClient


from inspection_hmi_gateway.recipe_store import RecipeStore
from inspection_hmi_gateway.result_store import ResultStore
from inspection_hmi_gateway.server.auth import hash_password
from inspection_hmi_gateway.server.main import create_app
from recipe_payloads import make_hmi_recipe_payload
from inspection_utils.config import save_yaml




@pytest.fixture(autouse=True)
def _gateway_test_env(monkeypatch):
    monkeypatch.setenv('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '1')

class _FakeEventBus:
    def attach_loop(self, _loop) -> None:
        return None

    async def connect(self, _websocket) -> None:
        return None

    def disconnect(self, _websocket) -> None:
        return None

    def make_message(self, event: str, payload: dict, *, event_type: str | None = None) -> dict:
        return {'event': event, 'type': event_type or event, 'payload': payload}



class _FakeState:
    def snapshot_payload(self) -> dict:
        return {
            'phase': 'READY',
            'mode': 'AUTO',
            'batchId': 'BATCH-API',
            'activeRecipeId': 'recipe-api',
            'activeRecipeName': 'API 配方',
            'cycleIndex': 12,
            'lastUpdatedAt': '2026-03-31T12:00:00Z',
            'guidance': 'ready',
            'supervisorMode': 'AUTO',
            'maintenance': {
                'requested': False,
                'enabled': False,
                'transitionState': 'LOCKED',
                'supervisorMode': 'AUTO',
                'source': 'test_fixture',
            },
        }

    def stats_payload(self) -> dict:
        return {
            'total': 2,
            'ok': 1,
            'ng': 1,
            'recheck': 0,
            'yieldRate': 0.5,
            'continuousRunCount': 2,
            'avgCycleMs': 123.0,
        }


class _FakeNode:
    def __init__(self, logs_root: Path, recipes_root: Path) -> None:
        self.state = _FakeState()
        self.recipe_store = RecipeStore(recipes_root)
        self.result_store = ResultStore(logs_root)
        self.recipe_store.save_from_hmi({'id': 'recipe-api', 'name': 'API 配方', 'version': '1.0.0', 'roi': [1, 2, 3, 4], 'qrRoi': [5, 6, 7, 8]})
        self.recipe_store.activate('recipe-api')
        self.app = self

    def refresh_recipes(self) -> list[dict]:
        default = self.recipe_store.current_default()
        active_recipe_id = str(default.get('recipe_id', '')) if isinstance(default, dict) else ''
        return [self.recipe_store.to_hmi_profile(item, active_recipe_id=active_recipe_id) for item in self.recipe_store.load_all()]

    def snapshot_payload(self) -> dict:
        return self.state.snapshot_payload()

    def stats_payload(self) -> dict:
        return self.state.stats_payload()

    def recipe_history(self, recipe_id: str) -> dict:
        return {
            'activations': self.recipe_store.list_activation_history(recipe_id=recipe_id),
            'revisions': self.recipe_store.list_revision_history(recipe_id=recipe_id),
        }

    def save_recipe(self, payload: dict) -> dict:
        recipe = self.recipe_store.save_from_hmi(payload)
        default = self.recipe_store.current_default()
        active_recipe_id = str(default.get('recipe_id', '')) if isinstance(default, dict) else ''
        profiles = [self.recipe_store.to_hmi_profile(item, active_recipe_id=active_recipe_id) for item in self.recipe_store.load_all()]
        target = next((item for item in profiles if item['id'] == str(recipe.get('recipe_id', ''))), None)
        if target is None:
            raise RuntimeError('配方保存后无法重新装载。')
        return target

    def activate_recipe(self, recipe_id: str, *, operator: str) -> dict:
        return self.recipe_store.activate(recipe_id, operator=operator)

    def result_detail(self, result_id: str):
        return self.result_store.get_result(result_id)

    def read_model_status(self) -> dict:
        return self.result_store.read_model_status()

    def repair_read_model(self) -> dict:
        self.result_store.repair_read_model()
        return self.result_store.read_model_status(refresh=False)

    def batch_summary(self, *, batch_id: str) -> dict:
        return self.result_store.batch_summary(batch_id=batch_id)

    def result_statistics(self, **filters):
        return self.result_store.query_statistics(**filters)

    def register_action_jobs(self, *, submit, get_job, cancel) -> None:
        self._action_submit = submit
        self._action_get_job = get_job
        self._action_cancel = cancel

    def register_action_executor_updates(self, handler) -> None:
        self._action_update_handler = handler

    def call_start(self, *args, **kwargs):
        return True, 'started'

    def publish_control(self, _action: str) -> None:
        return None

    def reset_fault(self):
        return True, 'reset'

    def new_batch(self) -> str:
        return 'BATCH-NEW'

    def run_diagnostic_action(self, action: str) -> dict:
        return {'action': action, 'success': True, 'message': 'ok', 'executedAt': '2026-03-31T12:00:00Z'}

    def request_maintenance_mode(self, enabled: bool, *, actor: str = 'anonymous') -> dict:
        return {
            **self.state.snapshot_payload(),
            'supervisorMode': 'AUTO',
            'maintenance': {
                'requested': bool(enabled),
                'enabled': False,
                'transitionState': 'ENTERING' if enabled else 'EXITING',
                'supervisorMode': 'AUTO',
                'source': actor,
            },
        }

    def artifact_url(self, path: str) -> str:
        normalized = str(path or '').replace('\\', '/').lstrip('/')
        return f'/artifacts/{normalized}' if normalized else ''

    def _artifact_url(self, path: str) -> str:
        return self.artifact_url(path)


class _FakeRuntime:
    def __init__(self, logs_root: Path, recipes_root: Path) -> None:
        self.event_bus = _FakeEventBus()
        self.node = _FakeNode(logs_root, recipes_root)

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None




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

def _write_logs(root: Path) -> None:
    (root / 'results').mkdir(parents=True, exist_ok=True)
    (root / 'events').mkdir(parents=True, exist_ok=True)
    (root / 'traces').mkdir(parents=True, exist_ok=True)
    (root / 'images').mkdir(parents=True, exist_ok=True)
    (root / 'images' / 'raw.png').write_bytes(b'raw-image')
    (root / 'images' / 'ann.png').write_bytes(b'annotated-image')
    with (root / 'results' / 'result_log.csv').open('w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['time', 'trace_id', 'batch_id', 'item_id', 'recipe_id', 'category', 'defect_type', 'score', 'qr_ok', 'qr_text', 'orientation_ok', 'color_name', 'color_ratio', 'image_path', 'annotated_image_path', 'detail_json'])
        writer.writerow(['2026-03-31T08:00:00Z', 'trace-api', 'BATCH-API', 1, 'recipe-api', 'COLOR', 'SHIFT', 0.81, True, 'QR100', True, 'red', 0.8, 'images/raw.png', 'images/ann.png', json.dumps({'warnings': ['偏色'], 'processing_ms': 18.2}, ensure_ascii=False)])
    with (root / 'results' / 'cycle_summary.jsonl').open('w', encoding='utf-8') as fh:
        fh.write(json.dumps({'trace_id': 'trace-api', 'decision': 'NG', 'cycle_time_sec': 0.3}, ensure_ascii=False) + '\n')




def _users_file(tmp_path: Path) -> Path:
    path = tmp_path / 'users.yaml'
    save_yaml(path, {
        'users': {
            'operator': {'password_hash': hash_password('operator123'), 'role': 'operator', 'display_name': '操作员'},
            'engineer': {'password_hash': hash_password('engineer123'), 'role': 'process_engineer', 'display_name': '工艺工程师'},
            'admin': {'password_hash': hash_password('admin123'), 'role': 'admin', 'display_name': '系统管理员'},
        }
    })
    return path

def _auth_header(client: TestClient, username: str, password: str) -> dict[str, str]:
    response = client.post('/api/v1/auth/login', json={'username': username, 'password': password})
    assert response.status_code == 200
    assert response.json().get('meta') in (None, {})
    assert 'inspection_session=' in response.headers.get('set-cookie', '')
    token = response.cookies.get('inspection_session')
    assert token
    return {'Authorization': f'Bearer {token}'}


def test_login_uses_cookie_session_by_default_and_legacy_header_is_opt_in(tmp_path: Path, monkeypatch) -> None:
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
        response = client.post('/api/v1/auth/login', json={'username': 'operator', 'password': 'operator123'})
        assert response.status_code == 200
        assert response.json().get('meta') in (None, {})
        assert response.cookies.get('inspection_session')

    monkeypatch.setenv('INSPECTION_HMI_ALLOW_LEGACY_BEARER_RESPONSE', '1')
    legacy_app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _FakeRuntime(logs_root, recipes_root),
    )
    with TestClient(legacy_app) as client:
        response = client.post('/api/v1/auth/login', json={'username': 'operator', 'password': 'operator123'}, headers={'x-inspection-return-token': '1'})
        assert response.status_code == 200
        assert response.json()['meta']['token']


def test_gateway_v1_auth_and_audit(tmp_path: Path) -> None:
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
        unauth = client.get('/api/v1/station/snapshot')
        assert unauth.status_code == 401

        operator_headers = _auth_header(client, 'operator', 'operator123')
        admin_headers = _auth_header(client, 'admin', 'admin123')

        snapshot = client.get('/api/v1/station/snapshot', headers=operator_headers)
        assert snapshot.status_code == 200
        assert snapshot.json()['data']['batchId'] == 'BATCH-API'

        start_resp = client.post('/api/v1/station/start', headers=operator_headers)
        assert start_resp.status_code == 404

        recipe_denied = client.post('/api/v1/recipes', headers=operator_headers, json=make_hmi_recipe_payload(recipe_id='recipe-new', name='新配方'))
        assert recipe_denied.status_code == 403

        export_resp = client.post('/api/v1/exports/BATCH-API', headers=operator_headers)
        assert export_resp.status_code == 200
        assert export_resp.json()['data']['exportUrl'].startswith('/artifacts/exports/')

        result_export = client.post('/api/v1/exports/results/trace-api', headers=operator_headers)
        assert result_export.status_code == 200
        assert result_export.json()['data']['scope'] == 'result'

        trace_export = client.post('/api/v1/exports/traces/trace-api', headers=operator_headers)
        assert trace_export.status_code == 200
        assert trace_export.json()['data']['scope'] == 'trace'

        audit_resp = client.get('/api/v1/audit', headers=admin_headers)
        assert audit_resp.status_code == 200
        actions = [item['action'] for item in audit_resp.json()['data']]
        assert 'STATION_START' not in actions
        assert 'EXPORT_BATCH' in actions
        assert 'EXPORT_RESULT' in actions
        assert 'EXPORT_TRACE' in actions


def test_gateway_v1_error_envelope_and_export_listing(tmp_path: Path) -> None:
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
        unauth = client.get('/api/v1/station/snapshot')
        assert unauth.status_code == 401
        body = unauth.json()
        assert body['success'] is False
        assert body['error']['code'] == 'HTTP_401'
        assert 'requestId' in body
        assert unauth.headers['x-request-id'] == body['requestId']

        operator_headers = _auth_header(client, 'operator', 'operator123')
        admin_headers = _auth_header(client, 'admin', 'admin123')
        client.post('/api/v1/exports/BATCH-API', headers=operator_headers)
        jobs = client.get('/api/v1/exports/jobs?limit=10&offset=0', headers=admin_headers)
        assert jobs.status_code == 200
        payload = jobs.json()
        assert payload['meta']['page']['total'] >= 1
        assert payload['data'][0]['batchId'] == 'BATCH-API'

        audit_resp = client.get('/api/v1/audit', headers=admin_headers)
        actions = [item['action'] for item in audit_resp.json()['data']]
        assert 'AUTH_LOGIN' in actions

        logout_resp = client.post('/api/v1/auth/logout', headers=operator_headers)
        assert logout_resp.status_code == 200

        audit_resp = client.get('/api/v1/audit', headers=admin_headers)
        actions = [item['action'] for item in audit_resp.json()['data']]
        assert 'AUTH_LOGOUT' in actions


def test_gateway_artifacts_require_auth_and_block_path_traversal(tmp_path: Path) -> None:
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
        unauth = client.get('/artifacts/images/raw.png')
        assert unauth.status_code == 401
        _auth_header(client, 'operator', 'operator123')
        ok = client.get('/artifacts/images/raw.png')
        assert ok.status_code == 200
        blocked = client.get('/artifacts/../outside.txt')
        assert blocked.status_code == 404


def test_gateway_cookie_session_and_change_password(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_HMI_BOOTSTRAP_PASSWORD', 'Bootstrap#123')
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(tmp_path / 'missing-users.yaml'),
        runtime_factory=lambda: _FakeRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        login_resp = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'Bootstrap#123'})
        assert login_resp.status_code == 200
        assert login_resp.json()['data']['mustChangePassword'] is True
        cookie_session = client.get('/api/v1/auth/session')
        assert cookie_session.status_code == 200
        assert cookie_session.json()['data']['username'] == 'admin'
        change_resp = client.post('/api/v1/auth/change-password', json={'currentPassword': 'Bootstrap#123', 'newPassword': 'Changed#Password1'})
        assert change_resp.status_code == 200
        post_change = client.get('/api/v1/auth/session')
        assert post_change.status_code == 401


def test_gateway_login_response_omits_bearer_token_by_default(tmp_path: Path) -> None:
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
        login_resp = client.post('/api/v1/auth/login', json={'username': 'operator', 'password': 'operator123'})
        assert login_resp.status_code == 200
        assert login_resp.json().get('meta') in (None, {})


def test_gateway_honors_custom_session_cookie_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_HMI_SESSION_COOKIE_NAME', 'custom_inspection_session')
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
        login_resp = client.post('/api/v1/auth/login', json={'username': 'operator', 'password': 'operator123'})
        assert login_resp.status_code == 200
        assert 'custom_inspection_session=' in login_resp.headers.get('set-cookie', '')
        cookie_session = client.get('/api/v1/auth/session')
        assert cookie_session.status_code == 200
        assert cookie_session.json()['data']['username'] == 'operator'


def test_process_engineer_can_manage_recipe_but_operator_cannot(tmp_path: Path) -> None:
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
        engineer_headers = _auth_header(client, 'engineer', 'engineer123')
        denied = client.post('/api/v1/recipes', headers=operator_headers, json=make_hmi_recipe_payload(recipe_id='recipe-new', name='新配方'))
        assert denied.status_code == 403
        allowed = client.post('/api/v1/recipes', headers=engineer_headers, json=make_hmi_recipe_payload(recipe_id='recipe-new', name='新配方'))
        assert allowed.status_code == 200


def test_gateway_result_detail_returns_trace_bundle(tmp_path: Path) -> None:
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    (logs_root / 'traces').mkdir(parents=True, exist_ok=True)
    (logs_root / 'traces' / 'trace-api.jsonl').write_text(json.dumps({'type': 'inspection_result', 'trace_id': 'trace-api'}, ensure_ascii=False) + '\n', encoding='utf-8')
    with (logs_root / 'results' / 'replay_manifest.jsonl').open('w', encoding='utf-8') as fh:
        fh.write(json.dumps({'trace_id': 'trace-api', 'trace_path': str(logs_root / 'traces' / 'trace-api.jsonl'), 'summary': {'trace_id': 'trace-api'}, 'run_artifacts': {'bag_recording': {'enabled': False}}}, ensure_ascii=False) + '\n')
    app = create_app(
        log_root=str(logs_root),
        recipe_root=str(recipes_root),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=lambda: _FakeRuntime(logs_root, recipes_root),
    )
    with TestClient(app) as client:
        operator_headers = _auth_header(client, 'operator', 'operator123')
        detail = client.get('/api/v1/results/trace-api', headers=operator_headers)
        assert detail.status_code == 200
        payload = detail.json()['data']
        assert payload['traceId'] == 'trace-api'
        assert payload['traceBundle']['traceId'] == 'trace-api'
        assert payload['traceBundle']['eventCount'] == 1



def test_removed_legacy_routes_return_not_found(tmp_path: Path) -> None:
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
        assert client.post('/api/v1/diagnostics/actions', headers=admin_headers, json={'action': 'CAPTURE_FRAME'}).status_code == 404
        assert client.post('/api/v1/station/start', headers=operator_headers).status_code == 404



def test_results_statistics_endpoint_is_query_driven(tmp_path: Path) -> None:
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
        response = client.get('/api/v1/results/statistics?sampleLimit=40', headers=operator_headers)
        assert response.status_code == 200
        payload = response.json()['data']
        assert payload['summary']['total'] == 1
        assert payload['summary']['ngCount'] == 1
        assert payload['summary']['yieldRate'] == 0
        assert payload['cycleTrend'][0]['recipeId'] == 'recipe-api'
        assert payload['recipeBreakdown'][0]['recipeName'] == 'API 配方'
        assert payload['readModelStatus']['querySurface'] == 'projection'


def test_action_capability_matrix_endpoint_returns_public_surface_only(tmp_path: Path) -> None:
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
        response = client.get('/api/v1/actions/capability-matrix', headers=operator_headers)
        assert response.status_code == 200
        payload = response.json()['data']
        assert 'run_calibration' not in payload
        assert 'run_benchmark' not in payload
        assert payload['set_maintenance_mode']['availability'] == 'production_ready'
        assert payload['diagnostic_capture_frame']['governance']['tier'] == 'official'


def test_internal_action_capability_matrix_endpoint_returns_empty_internal_surface(tmp_path: Path) -> None:
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
        response = client.get('/api/internal/actions/capability-matrix', headers=admin_headers)
        assert response.status_code == 404


def test_compatibility_routes_are_removed_and_canonical_plane_remains_available(tmp_path: Path) -> None:
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
        legacy = client.post('/api/v1/station/start', headers=operator_headers)
        assert legacy.status_code == 404

        canonical = client.post('/api/v1/actions/start-batch', headers=operator_headers, json={'recipeId': 'recipe-api', 'batchId': 'BATCH-API'})
        assert canonical.status_code == 200
        assert canonical.json()['data']['kind'] == 'start_batch'
