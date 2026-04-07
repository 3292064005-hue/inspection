from __future__ import annotations

import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from inspection_utils.logging_tools import safe_json_loads

from .responses import utc_now

LOGGER = logging.getLogger(__name__)


async def handle_gateway_websocket(*, websocket: WebSocket, auth_service: Any, event_bus: Any, context: Any) -> None:
    """Authenticate, initialize, and serve the gateway WebSocket session."""
    ticket = websocket.query_params.get('ticket', '')
    token = websocket.query_params.get('token', '')
    session = auth_service.resolve_websocket_session(ticket=ticket, token=token)
    if session is None:
        await websocket.close(code=4401)
        return
    await websocket.accept()
    if event_bus is not None:
        await event_bus.connect(websocket)
    try:
        app_facade = context.app()
        if event_bus is not None:
            await websocket.send_json(event_bus.make_message('gateway.status', {'mode': 'http', 'transport': 'ONLINE', 'httpOk': True, 'wsOk': True, 'retryCount': 0, 'lastError': '', 'updatedAt': utc_now(),}))
            await websocket.send_json(event_bus.make_message('auth.session', {k: v for k, v in session.items() if k != 'token'}))
            await websocket.send_json(event_bus.make_message('station.state.updated', app_facade.snapshot_payload()))
            await websocket.send_json(event_bus.make_message('station.count.updated', app_facade.stats_payload()))
        while True:
            raw_text = await websocket.receive_text()
            payload = safe_json_loads(raw_text or '{}')
            msg_type = str(payload.get('type', '')).lower() if isinstance(payload, dict) else ''
            if msg_type == 'ping':
                if event_bus is not None:
                    await websocket.send_json(event_bus.make_message('gateway.pong', {'timestamp': utc_now()}, event_type='pong'))
                else:
                    await websocket.send_json({'type': 'pong', 'payload': {'timestamp': utc_now()}})
    except WebSocketDisconnect:
        if event_bus is not None:
            event_bus.disconnect(websocket)
    except Exception as exc:  # pragma: no cover - transport safety net
        LOGGER.exception('WebSocket session failed. client=%s', getattr(websocket, 'client', None), exc_info=exc)
        if event_bus is not None:
            event_bus.disconnect(websocket)
