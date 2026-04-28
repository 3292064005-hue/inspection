from __future__ import annotations

from pathlib import Path

from inspection_utils.io_common import resolve_resource_path
from typing import Any

from .auth import AuthService
from .context import GatewayAppContext
from .persistence import MetadataRepository


def build_gateway_context(*, runtime: Any, log_root: Path, recipe_root: Path, frontend_dist: Path, users_path: Path) -> GatewayAppContext:
    """Construct the gateway composition root."""
    metadata_repository = MetadataRepository(log_root / 'gateway_metadata.sqlite3')
    telemetry_config_path = resolve_resource_path('config/system/telemetry.yaml', package_name='inspection_hmi_gateway', start=__file__)
    auth_service = AuthService(metadata_repository, users_path=users_path)
    return GatewayAppContext(
        runtime=runtime,
        log_root=log_root,
        recipe_root=recipe_root,
        frontend_dist=frontend_dist,
        telemetry_config_path=telemetry_config_path,
        metadata_repository=metadata_repository,
        auth_service=auth_service,
    )
