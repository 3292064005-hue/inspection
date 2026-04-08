from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from inspection_hmi_gateway.server.auth import hash_password
from inspection_hmi_gateway.server.main import create_app
from inspection_utils.config import save_yaml


class _Runtime:
    def __init__(self) -> None:
        self.node = object()

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def health(self) -> dict:
        return {
            'mode': 'embedded',
            'runtimeReady': True,
            'nodeReady': True,
            'executorReady': True,
            'spinThreadAlive': True,
            'stateVersion': 7,
            'actionExecution': {
                'transportMode': 'executor_bridge',
                'actionExecutorExpected': True,
                'nativeActionClientEnabled': False,
                'transportReady': True,
                'transportObserved': True,
                'executorUpdateChannelBound': True,
                'receivedExecutorUpdates': 2,
            },
        }


def _users_file(tmp_path: Path) -> Path:
    path = tmp_path / 'users.yaml'
    save_yaml(path, {'users': {'viewer': {'password_hash': hash_password('viewer123'), 'role': 'viewer', 'display_name': '查看者'}}})
    return path


def test_health_endpoint_surfaces_runtime_health_payload(tmp_path: Path) -> None:
    app = create_app(
        log_root=str(tmp_path / 'logs'),
        recipe_root=str(tmp_path / 'recipes'),
        frontend_dist=str(tmp_path / 'frontend_dist_missing'),
        users_path=str(_users_file(tmp_path)),
        runtime_factory=_Runtime,
    )
    with TestClient(app) as client:
        response = client.get('/api/v1/health')
        assert response.status_code == 200
        payload = response.json()['data']
        assert payload['runtimeReady'] is True
        assert payload['runtime']['spinThreadAlive'] is True
        assert payload['runtime']['stateVersion'] == 7
        assert payload['actionExecution']['transportMode'] == 'executor_bridge'
        assert payload['actionExecution']['transportReady'] is True
        assert payload['actionExecution']['transportObserved'] is True
