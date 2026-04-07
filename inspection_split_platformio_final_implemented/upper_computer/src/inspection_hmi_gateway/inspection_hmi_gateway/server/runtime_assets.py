from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from inspection_utils.paths import resolve_resource_path, resolve_runtime_path


@dataclass(frozen=True, slots=True)
class GatewayResolvedPaths:
    log_root: Path
    recipe_root: Path
    frontend_dist: Path
    users_path: Path
    require_frontend_dist: bool


def parse_bool_env(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name, '').strip()
    if not raw:
        return default
    lowered = raw.lower()
    if lowered in {'1', 'true', 'yes', 'on'}: return True
    if lowered in {'0', 'false', 'no', 'off'}: return False
    raise ValueError(f'{name} must be a boolean-like value, got {raw!r}')


def resolve_gateway_paths(*, log_root: str, recipe_root: str, frontend_dist: str, users_path: str, require_frontend_dist: bool | None) -> GatewayResolvedPaths:
    strict_frontend = parse_bool_env('INSPECTION_HMI_REQUIRE_FRONTEND_DIST', default=False) if require_frontend_dist is None else bool(require_frontend_dist)
    resolved = GatewayResolvedPaths(log_root=resolve_runtime_path(log_root, start=__file__), recipe_root=resolve_runtime_path(recipe_root, start=__file__), frontend_dist=resolve_resource_path(frontend_dist, package_name='inspection_hmi_gateway', start=__file__), users_path=resolve_resource_path(users_path, package_name='inspection_hmi_gateway', start=__file__), require_frontend_dist=strict_frontend)
    if resolved.require_frontend_dist:
        index_path = resolved.frontend_dist / 'index.html'
        if not resolved.frontend_dist.exists() or not index_path.exists():
            raise FileNotFoundError(f'Frontend dist is required but missing: expected {index_path}. Build the frontend before starting the release gateway.')
    return resolved
