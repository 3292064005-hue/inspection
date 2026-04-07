from __future__ import annotations

from pathlib import Path

from inspection_utils.paths import resolve_resource_path


def test_resolve_resource_path_returns_absolute_path_for_existing_relative_resource() -> None:
    root = Path(__file__).resolve().parents[2]
    original_cwd = Path.cwd()
    try:
        # Reproduce the launch/runtime case where the current working directory is the workspace root.
        import os
        os.chdir(root)
        resolved = resolve_resource_path('config/profiles/production.yaml', package_name='inspection_bringup', start=__file__)
    finally:
        os.chdir(original_cwd)

    assert resolved.is_absolute()
    assert resolved == (root / 'config' / 'profiles' / 'production.yaml').resolve()
