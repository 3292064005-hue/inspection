from __future__ import annotations

"""Shared HTTP transport helpers for gateway action routes.

This module keeps the standard action plane and the legacy compatibility
façades aligned on transport semantics so policy, dispatch, and runtime
failures cannot drift across routers.
"""

from typing import Mapping, NoReturn

from fastapi import HTTPException

from ..action_contract import ActionDispatchError, ActionPolicyError

COMPATIBILITY_HEADERS: dict[str, str] = {
    'X-Inspection-Compatibility-Route': 'true',
    'X-Inspection-Canonical-Action-Plane': '/api/v1/actions/*',
}


def compat_headers(*, route: str) -> dict[str, str]:
    """Return immutable headers advertising compatibility-route status.

    Args:
        route: Concrete legacy HTTP route serving as a façade.

    Returns:
        Header mapping safe to attach to the response.

    Boundary behavior:
        The canonical control plane remains discoverable even when older
        clients continue to use a compatibility route.
    """
    return {
        **COMPATIBILITY_HEADERS,
        'X-Inspection-Compatibility-Route-Name': str(route or '').strip(),
    }



def raise_action_http_error(
    exc: Exception,
    *,
    invalid_status: int = 400,
    runtime_status: int = 409,
    runtime_code: str = 'action_execution_failed',
    headers: Mapping[str, str] | None = None,
) -> NoReturn:
    """Translate domain/transport exceptions into consistent HTTP failures.

    Args:
        exc: Original domain exception.
        invalid_status: HTTP status for caller input errors.
        runtime_status: HTTP status for synchronous façade runtime failures.
        runtime_code: Machine-readable code used for ``RuntimeError`` payloads.
        headers: Optional HTTP headers preserved on error responses.

    Raises:
        HTTPException: Always raised with normalized ``detail`` payload.
        Exception: Re-raises unknown exception types unchanged.

    Boundary behavior:
        Compatibility façades synchronously wait on persisted action jobs.
        A terminal job failure therefore surfaces as a structured HTTP error
        instead of an opaque string mismatch versus the canonical action plane.
    """
    normalized_headers = {str(key): str(value) for key, value in dict(headers or {}).items()}
    if isinstance(exc, ActionPolicyError):
        raise HTTPException(status_code=409, detail=exc.to_payload(), headers=normalized_headers) from exc
    if isinstance(exc, ActionDispatchError):
        raise HTTPException(status_code=503, detail=exc.to_payload(), headers=normalized_headers) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(status_code=invalid_status, detail=str(exc), headers=normalized_headers) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(
            status_code=runtime_status,
            detail={
                'code': str(runtime_code or 'action_execution_failed'),
                'message': str(exc) or '动作执行失败。',
            },
            headers=normalized_headers,
        ) from exc
    raise exc
