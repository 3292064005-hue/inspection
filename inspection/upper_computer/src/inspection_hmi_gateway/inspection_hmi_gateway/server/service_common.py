from __future__ import annotations

"""Shared helpers for binding HTTP services to the gateway application planes."""

from types import SimpleNamespace
from typing import Any

from .context import GatewayAppContext


def app_service(context: GatewayAppContext) -> Any:
    """Return the authoritative gateway runtime application service."""
    return context.app()


def app_boundary(context: GatewayAppContext) -> Any:
    """Return the authoritative split gateway application boundary.

    Args:
        context: Bound gateway application context.

    Returns:
        Boundary object exposing the recipe/control/query planes and shared
        state store.

    Raises:
        RuntimeError: When neither the runtime boundary nor the minimal plane
            fallback attributes are available.

    Boundary behavior:
        Production runtimes must expose ``boundary`` directly from
        ``GatewayApplicationService``. A narrow attribute fallback remains for
        schema export and unit-test doubles so service modules can reuse the
        same plane contract without restoring removed HTTP compatibility routes.
    """
    app = app_service(context)
    boundary = getattr(app, 'boundary', None)
    if boundary is not None:
        return boundary
    state_store_obj = getattr(app, 'state_store', None) or getattr(app, 'state', None)
    recipe_plane_obj = getattr(app, 'recipe_plane', None) or SimpleNamespace(service=app)
    control_plane_obj = getattr(app, 'control_plane', None) or SimpleNamespace(station=app)
    query_plane_obj = getattr(app, 'query_plane', None) or SimpleNamespace(results=app)
    if state_store_obj is None:
        raise RuntimeError('gateway application service must expose state_store or state')
    return SimpleNamespace(
        state_store=state_store_obj,
        recipe_plane=recipe_plane_obj,
        control_plane=control_plane_obj,
        query_plane=query_plane_obj,
    )


def state_store(context: GatewayAppContext) -> Any:
    """Return the authoritative gateway state store."""
    return app_boundary(context).state_store


def recipe_plane(context: GatewayAppContext) -> Any:
    """Return the authoritative recipe plane."""
    return app_boundary(context).recipe_plane


def control_plane(context: GatewayAppContext) -> Any:
    """Return the authoritative control plane."""
    return app_boundary(context).control_plane


def query_plane(context: GatewayAppContext) -> Any:
    """Return the authoritative query plane."""
    return app_boundary(context).query_plane
