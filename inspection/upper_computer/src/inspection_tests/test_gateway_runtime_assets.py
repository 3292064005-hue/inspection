from pathlib import Path

import pytest

from inspection_hmi_gateway.server.runtime_assets import resolve_gateway_paths


def test_resolve_gateway_paths_anchors_users_and_recipes_under_runtime_root(tmp_path, monkeypatch) -> None:
    runtime_root = tmp_path / 'runtime'
    frontend = tmp_path / 'frontend'
    (frontend / 'assets').mkdir(parents=True)
    (frontend / 'index.html').write_text('<html></html>', encoding='utf-8')
    monkeypatch.setenv('INSPECTION_RUNTIME_ROOT', str(runtime_root))

    resolved = resolve_gateway_paths(
        log_root='logs/runtime',
        recipe_root='config/recipes',
        frontend_dist=str(frontend),
        users_path='config/system/hmi_users.yaml',
        require_frontend_dist=True,
    )

    assert resolved.log_root == runtime_root / 'logs/runtime'
    assert resolved.recipe_root == runtime_root / 'config/recipes'
    assert resolved.users_path == runtime_root / 'config/system/hmi_users.yaml'


def test_resolve_gateway_paths_rejects_file_backed_log_root(tmp_path, monkeypatch) -> None:
    runtime_root = tmp_path / 'runtime'
    frontend = tmp_path / 'frontend'
    (frontend / 'assets').mkdir(parents=True)
    (frontend / 'index.html').write_text('<html></html>', encoding='utf-8')
    monkeypatch.setenv('INSPECTION_RUNTIME_ROOT', str(runtime_root))
    conflict = runtime_root / 'logs/runtime'
    conflict.parent.mkdir(parents=True, exist_ok=True)
    conflict.write_text('not-a-directory', encoding='utf-8')

    with pytest.raises(NotADirectoryError):
        resolve_gateway_paths(
            log_root='logs/runtime',
            recipe_root='config/recipes',
            frontend_dist=str(frontend),
            users_path='config/system/hmi_users.yaml',
            require_frontend_dist=True,
        )
