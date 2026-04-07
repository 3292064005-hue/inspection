from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .paths import resolve_resource_path


def load_yaml(path: str | os.PathLike, *, package_name: str = 'inspection_utils', start: str | os.PathLike | None = None) -> dict:
    """Load a YAML mapping from a resolved resource path."""
    resolved = resolve_resource_path(path, package_name=package_name, start=start or __file__)
    with open(resolved, 'r', encoding='utf-8') as handle:
        return yaml.safe_load(handle) or {}


def save_yaml(path: str | os.PathLike, data: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', encoding='utf-8') as handle:
        yaml.safe_dump(data, handle, allow_unicode=True, sort_keys=False)


def deep_get(data: dict, keys: list[str], default=None):
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def ensure_dir(path: str | os.PathLike) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target
