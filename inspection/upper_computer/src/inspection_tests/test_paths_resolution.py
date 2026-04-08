from __future__ import annotations

from inspection_utils.paths import (
    default_runtime_root,
    repo_root,
    resolve_log_artifact_path,
    resolve_resource_path,
    resolve_runtime_path,
    resolve_workspace_path,
)


def test_repo_root_finds_workspace() -> None:
    root = repo_root(__file__)
    assert (root / 'src').exists()
    assert (root / 'config').exists()


def test_resolve_workspace_path_prefers_existing_relative_target() -> None:
    resolved = resolve_workspace_path('config/system/hmi_users.yaml', package_name='inspection_utils', start=__file__)
    assert resolved.exists()
    assert resolved.name == 'hmi_users.yaml'


def test_resolve_resource_path_prefers_existing_workspace_resource() -> None:
    resolved = resolve_resource_path('config/recipes/default_recipe.yaml', package_name='inspection_bringup', start=__file__)
    assert resolved.exists()
    assert resolved.name == 'default_recipe.yaml'


def test_resolve_runtime_path_anchors_missing_relative_paths_under_runtime_root(monkeypatch, tmp_path) -> None:
    runtime_root = tmp_path / 'runtime-root'
    monkeypatch.setenv('INSPECTION_RUNTIME_ROOT', str(runtime_root))
    resolved = resolve_runtime_path('logs/runtime/session/new-dir', start=tmp_path / 'outside' / 'module.py')
    assert resolved == runtime_root / 'logs' / 'runtime' / 'session' / 'new-dir'


def test_default_runtime_root_prefers_workspace_in_source_mode() -> None:
    root = default_runtime_root(start=__file__)
    assert root == repo_root(__file__)


def test_resolve_log_artifact_path_blocks_escape(tmp_path) -> None:
    log_root = tmp_path / 'logs'
    (log_root / 'images').mkdir(parents=True, exist_ok=True)
    inside = log_root / 'images' / 'sample.png'
    inside.write_bytes(b'png')

    assert resolve_log_artifact_path(log_root, 'images/sample.png') == inside.resolve()
    assert resolve_log_artifact_path(log_root, str(inside)) == inside.resolve()

    outside = tmp_path / 'outside.txt'
    outside.write_text('nope', encoding='utf-8')
    try:
        resolve_log_artifact_path(log_root, str(outside))
    except ValueError as exc:
        assert 'outside log root' in str(exc)
    else:
        raise AssertionError('expected ValueError for escaped artifact path')
