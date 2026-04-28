from __future__ import annotations

"""Shared HTTP error translation helpers for canonical gateway routes."""

from typing import Mapping, NoReturn

from fastapi import HTTPException

from ..action_contract import ActionDispatchError, ActionPolicyError


def raise_action_http_error(
    exc: Exception,
    *,
    invalid_status: int = 400,
    runtime_status: int = 409,
    runtime_code: str = 'action_execution_failed',
    headers: Mapping[str, str] | None = None,
) -> NoReturn:
    """Translate domain and transport exceptions into consistent HTTP failures.

    Args:
        exc: Domain or transport exception raised by the service layer.
        invalid_status: HTTP status used for request/value validation errors.
        runtime_status: HTTP status used for runtime failures.
        runtime_code: Canonical error code for runtime failures.
        headers: Optional response headers to preserve.

    Returns:
        Never returns. Always raises ``HTTPException`` or re-raises ``exc``.

    Raises:
        HTTPException: For mapped action-policy, dispatch, validation, or runtime
            failures.
        Exception: Re-raises unknown exception types unchanged.

    Boundary behavior:
        The canonical action plane no longer carries compatibility-route headers.
        Transport semantics are now shared only across first-party public routes.
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
