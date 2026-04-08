from __future__ import annotations

from typing import Any

from .context import GatewayAppContext


def app_facade(context: GatewayAppContext) -> Any:
    app_fn = getattr(context, 'app', None)
    if callable(app_fn):
        return app_fn()
    node_fn = getattr(context, 'node', None)
    if callable(node_fn):
        return node_fn()
    return context
