from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from inspection_hmi_gateway.server.main import create_app
from inspection_hmi_gateway.server.auth import hash_password
from inspection_utils.config import save_yaml


class _FakeRuntime:
    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None


def _users_file(tmp_path):
    path = tmp_path / 'users.yaml'
    save_yaml(path, {'users': {'admin': {'password_hash': hash_password('admin123'), 'role': 'admin', 'display_name': '系统管理员'}}})
    return path


def test_unhandled_exception_does_not_leak_raw_error_message(tmp_path) -> None:
    app = create_app(
        log_root=str(tmp_path / 'logs'),
        recipe_root=str(tmp_path / 'recipes'),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=_FakeRuntime,
    )
    router = APIRouter()

    @router.get('/api/v1/test-crash')
    async def crash() -> dict:
        raise RuntimeError('sensitive-internal-detail')

    app.include_router(router)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get('/api/v1/test-crash')

    assert response.status_code == 500
    payload = response.json()
    assert payload['error']['code'] == 'INTERNAL_SERVER_ERROR'
    assert 'sensitive-internal-detail' not in str(payload)
