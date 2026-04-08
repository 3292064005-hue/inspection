from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def api_ok(data: Any = None, *, meta: dict[str, Any] | None = None, message: str = 'ok') -> dict[str, Any]:
    payload: dict[str, Any] = {
        'success': True,
        'message': message,
        'data': data,
        'timestamp': utc_now(),
    }
    if meta is not None:
        payload['meta'] = meta
    return payload


def page_meta(*, limit: int, offset: int, total: int) -> dict[str, Any]:
    next_offset = offset + limit if offset + limit < total else None
    return {
        'page': {
            'limit': limit,
            'offset': offset,
            'total': total,
            'hasNext': next_offset is not None,
            'nextOffset': next_offset,
        }
    }


def api_error(message: str, *, code: str = 'ERROR', detail: Any = None, status_code: int | None = None, request_id: str = '') -> dict[str, Any]:
    payload: dict[str, Any] = {
        'success': False,
        'message': message,
        'error': {
            'code': code,
            'detail': detail,
        },
        'timestamp': utc_now(),
    }
    if status_code is not None:
        payload['statusCode'] = status_code
    if request_id:
        payload['requestId'] = request_id
    return payload


def page_ok(items: list[dict[str, Any]], *, total: int, limit: int, offset: int, message: str = "ok") -> dict[str, Any]:
    return api_ok(items, meta=page_meta(limit=limit, offset=offset, total=total), message=message)
