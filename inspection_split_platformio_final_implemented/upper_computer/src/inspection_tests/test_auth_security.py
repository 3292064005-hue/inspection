from __future__ import annotations

from inspection_hmi_gateway.server.auth import AuthService, hash_password, verify_password
from inspection_hmi_gateway.server.main import create_app
from inspection_hmi_gateway.server.persistence import MetadataRepository, token_digest
from inspection_utils.config import save_yaml


class _MinimalRuntime:
    def __init__(self):
        self.event_bus = None

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None




def test_password_hash_roundtrip() -> None:
    encoded = hash_password('secret-123')
    assert encoded.startswith('pbkdf2_sha256$')
    assert verify_password('secret-123', encoded) is True
    assert verify_password('bad-password', encoded) is False


def test_auth_service_bootstrap_admin_and_ws_ticket(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_HMI_BOOTSTRAP_PASSWORD', 'Bootstrap#123')
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    service = AuthService(repository, users_path=tmp_path / 'missing-users.yaml')
    session = service.login(username='admin', password='Bootstrap#123')
    assert session['role'] == 'admin'
    assert session['bootstrap'] is True
    ticket = service.issue_ws_ticket(session['token'])
    assert ticket['ticket']
    resolved = service.consume_ws_ticket(ticket['ticket'])
    assert resolved is not None and resolved['username'] == 'admin'
    assert service.consume_ws_ticket(ticket['ticket']) is None


def test_auth_service_loads_hashed_users_file(tmp_path) -> None:
    users_path = tmp_path / 'users.yaml'
    save_yaml(users_path, {'users': {'maintainer': {'password_hash': hash_password('maintainer#123'), 'role': 'maintainer', 'display_name': '维护工程师'}}})
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    service = AuthService(repository, users_path=users_path)
    session = service.login(username='maintainer', password='maintainer#123')
    assert session['role'] == 'maintainer'
    assert session['bootstrap'] is False


def test_auth_service_changes_password_and_cleans_bootstrap_artifacts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_HMI_BOOTSTRAP_PASSWORD', 'Bootstrap#123')
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    users_path = tmp_path / 'config' / 'users.yaml'
    service = AuthService(repository, users_path=users_path)
    session = service.login(username='admin', password='Bootstrap#123')
    result = service.change_password(session_token=session['token'], current_password='Bootstrap#123', new_password='Changed#Password1')
    assert result['passwordChanged'] is True
    assert service.resolve(session['token']) is None
    assert service.login(username='admin', password='Changed#Password1')['bootstrap'] is False
    assert not (repository.path.parent / 'bootstrap' / 'bootstrap_admin.yaml').exists()


def test_repository_never_stores_raw_session_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_HMI_BOOTSTRAP_PASSWORD', 'Bootstrap#123')
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    service = AuthService(repository, users_path=tmp_path / 'users.yaml')
    session = service.login(username='admin', password='Bootstrap#123')
    import sqlite3
    conn = sqlite3.connect(repository.path)
    try:
        row = conn.execute('SELECT token_digest FROM operator_session').fetchone()
        assert row is not None
        assert row[0] == token_digest(session['token'])
        assert row[0] != session['token']
    finally:
        conn.close()


def test_auth_service_websocket_resolution_prefers_ticket_and_disables_raw_token_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_HMI_BOOTSTRAP_PASSWORD', 'Bootstrap#123')
    monkeypatch.delenv('INSPECTION_HMI_ALLOW_LEGACY_WS_TOKEN', raising=False)
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    service = AuthService(repository, users_path=tmp_path / 'missing-users.yaml')
    session = service.login(username='admin', password='Bootstrap#123')

    assert service.resolve_websocket_session(ticket='', token=session['token']) is None

    ticket = service.issue_ws_ticket(session['token'])
    resolved = service.resolve_websocket_session(ticket=ticket['ticket'], token='')
    assert resolved is not None
    assert resolved['username'] == 'admin'


def test_auth_service_can_reenable_legacy_websocket_token_resolution(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_HMI_BOOTSTRAP_PASSWORD', 'Bootstrap#123')
    monkeypatch.setenv('INSPECTION_HMI_ALLOW_LEGACY_WS_TOKEN', '1')
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    service = AuthService(repository, users_path=tmp_path / 'missing-users.yaml')
    session = service.login(username='admin', password='Bootstrap#123')

    resolved = service.resolve_websocket_session(ticket='', token=session['token'])
    assert resolved is not None
    assert resolved['username'] == 'admin'



def test_login_disables_legacy_bearer_response_by_default(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv('INSPECTION_HMI_BOOTSTRAP_PASSWORD', 'Bootstrap#123')
    monkeypatch.delenv('INSPECTION_HMI_ALLOW_LEGACY_BEARER_RESPONSE', raising=False)
    app = create_app(
        log_root=str(tmp_path / 'logs'),
        recipe_root=str(tmp_path / 'recipes'),
        frontend_dist=str(tmp_path / 'frontend_dist'),
        users_path=str(tmp_path / 'missing-users.yaml'),
        runtime_factory=lambda: _MinimalRuntime(),
    )
    with TestClient(app) as client:
        response = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'Bootstrap#123'}, headers={'x-inspection-return-token': '1'})
        assert response.status_code == 200
        assert response.json().get('meta') in (None, {})
        assert response.cookies.get('inspection_session')


def test_login_can_opt_in_legacy_bearer_response_via_env(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv('INSPECTION_HMI_BOOTSTRAP_PASSWORD', 'Bootstrap#123')
    monkeypatch.setenv('INSPECTION_HMI_ALLOW_LEGACY_BEARER_RESPONSE', '1')
    app = create_app(
        log_root=str(tmp_path / 'logs'),
        recipe_root=str(tmp_path / 'recipes'),
        frontend_dist=str(tmp_path / 'frontend_dist'),
        users_path=str(tmp_path / 'missing-users.yaml'),
        runtime_factory=lambda: _MinimalRuntime(),
    )
    with TestClient(app) as client:
        response = client.post('/api/v1/auth/login', json={'username': 'admin', 'password': 'Bootstrap#123'}, headers={'x-inspection-return-token': '1'})
        assert response.status_code == 200
        assert response.json()['meta']['token']


def test_auth_service_strict_user_config_fails_fast_on_invalid_yaml(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv('INSPECTION_HMI_STRICT_USER_CONFIG', '1')
    users_path = tmp_path / 'users.yaml'
    save_yaml(users_path, {'users': {'broken': {'role': 'viewer'}}})
    repository = MetadataRepository(tmp_path / 'runtime' / 'gateway.sqlite3')
    try:
        AuthService(repository, users_path=users_path)
    except RuntimeError as exc:
        assert '用户配置' in str(exc)
    else:
        raise AssertionError('strict user config must fail fast when the users file is malformed')
