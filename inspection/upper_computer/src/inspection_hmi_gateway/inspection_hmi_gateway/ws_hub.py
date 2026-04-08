from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass
from typing import Any

from .runtime_components import utc_now


@dataclass(slots=True)
class WebSocketHubMetrics:
    active_connections: int
    backlog_size: int
    max_backlog_size: int
    dropped_connections: int
    published_messages: int
    publish_failures: int
    last_error: str
    send_timeout_sec: float
    coalesced_messages: int
    filtered_messages: int

    def to_dict(self) -> dict[str, Any]:
        return {
            'activeConnections': int(self.active_connections),
            'backlogSize': int(self.backlog_size),
            'maxBacklogSize': int(self.max_backlog_size),
            'droppedConnections': int(self.dropped_connections),
            'publishedMessages': int(self.published_messages),
            'publishFailures': int(self.publish_failures),
            'lastError': str(self.last_error),
            'sendTimeoutSec': float(self.send_timeout_sec),
            'coalescedMessages': int(self.coalesced_messages),
            'filteredMessages': int(self.filtered_messages),
        }


class GatewayWebSocketHub:
    """Gateway WebSocket fan-out with bounded backlog and topic filtering."""

    _COALESCED_EVENTS = {'station.state.updated', 'station.count.updated', 'system.heartbeat', 'gateway.status'}

    def __init__(self, *, backlog_size: int = 128, send_timeout_sec: float = 5.0, drop_slow_connections: bool = True) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.connections: set[Any] = set()
        self._subscriptions: dict[Any, frozenset[str]] = {}
        self.recent_messages: deque[dict[str, Any]] = deque(maxlen=max(1, int(backlog_size)))
        self.lock = threading.Lock()
        self._seq = 0
        self._dropped_connections = 0
        self._published_messages = 0
        self._publish_failures = 0
        self._last_error = ''
        self._send_timeout_sec = max(0.0, float(send_timeout_sec))
        self._drop_slow_connections = bool(drop_slow_connections)
        self._coalesced_messages = 0
        self._filtered_messages = 0

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self._last_error = ''

    def _record_publish_error(self, exc: BaseException | str) -> None:
        with self.lock:
            self._publish_failures += 1
            self._last_error = str(exc)

    def _event_topic(self, event: str) -> str:
        head = str(event or '').split('.', 1)[0].strip().lower()
        return head or 'misc'

    def _subscriptions_for(self, websocket: Any) -> frozenset[str]:
        params = getattr(websocket, 'query_params', None)
        raw = ''
        if params is not None and hasattr(params, 'get'):
            raw = str(params.get('topics', '') or params.get('topic', '') or '')
        topics = {item.strip().lower() for item in raw.split(',') if item.strip()}
        return frozenset(topics)

    def _accepts(self, websocket: Any, message: dict[str, Any]) -> bool:
        subscriptions = self._subscriptions.get(websocket, frozenset())
        if not subscriptions:
            return True
        topic = str(message.get('topic', '')).lower()
        event = str(message.get('event', '')).lower()
        return topic in subscriptions or event in subscriptions

    def make_message(self, event: str, payload: dict[str, Any], *, event_type: str | None = None) -> dict[str, Any]:
        with self.lock:
            self._seq += 1
            seq = self._seq
        message = {
            'event': event,
            'topic': self._event_topic(event),
            'type': event_type or event,
            'version': 1,
            'seq': seq,
            'ts': utc_now(),
            'payload': payload,
        }
        if isinstance(payload, dict):
            for src_key, dst_key in (
                ('traceId', 'traceId'),
                ('trace_id', 'traceId'),
                ('batchId', 'batchId'),
                ('batch_id', 'batchId'),
                ('correlationId', 'correlationId'),
            ):
                value = payload.get(src_key)
                if value:
                    message[dst_key] = value
        return message

    async def _send_json(self, websocket: Any, message: dict[str, Any]) -> None:
        coro = websocket.send_json(message)
        if self._send_timeout_sec > 0:
            await asyncio.wait_for(coro, timeout=self._send_timeout_sec)
        else:
            await coro

    async def _close_socket(self, websocket: Any) -> None:
        close_callable = getattr(websocket, 'close', None)
        if close_callable is None:
            return
        result = close_callable()
        if asyncio.iscoroutine(result):
            await result

    def _append_backlog(self, message: dict[str, Any]) -> None:
        if message['event'] in self._COALESCED_EVENTS:
            for index in range(len(self.recent_messages) - 1, -1, -1):
                if self.recent_messages[index].get('event') == message['event']:
                    del self.recent_messages[index]
                    self._coalesced_messages += 1
                    break
        self.recent_messages.append(message)

    async def connect(self, websocket: Any) -> None:
        subscriptions = self._subscriptions_for(websocket)
        with self.lock:
            self.connections.add(websocket)
            self._subscriptions[websocket] = subscriptions
            backlog = [message for message in self.recent_messages if self._accepts(websocket, message)]
        for message in backlog:
            try:
                await self._send_json(websocket, message)
            except Exception as exc:
                self._record_publish_error(exc)
                self.disconnect(websocket)
                if self._drop_slow_connections:
                    try:
                        await self._close_socket(websocket)
                    except Exception as close_exc:
                        self._record_publish_error(close_exc)
                return

    def disconnect(self, websocket: Any) -> None:
        with self.lock:
            removed = websocket in self.connections
            self.connections.discard(websocket)
            self._subscriptions.pop(websocket, None)
            if removed:
                self._dropped_connections += 1

    def broadcast(self, event: str, payload: dict[str, Any]) -> None:
        loop = self.loop
        if loop is None:
            self._record_publish_error('websocket loop is not attached')
            return
        message = self.make_message(event, payload)
        with self.lock:
            self._append_backlog(message)
            self._published_messages += 1
        try:
            future = asyncio.run_coroutine_threadsafe(self._broadcast_async(message), loop)
        except Exception as exc:
            self._record_publish_error(exc)
            return

        def _done_callback(done_future: Any) -> None:
            try:
                done_future.result()
            except Exception as exc:
                self._record_publish_error(exc)

        future.add_done_callback(_done_callback)

    async def _broadcast_async(self, message: dict[str, Any]) -> None:
        dead: list[Any] = []
        filtered = 0
        with self.lock:
            sockets = list(self.connections)
        for websocket in sockets:
            if not self._accepts(websocket, message):
                filtered += 1
                continue
            try:
                await self._send_json(websocket, message)
            except Exception as exc:
                dead.append(websocket)
                self._record_publish_error(exc)
                if self._drop_slow_connections:
                    try:
                        await self._close_socket(websocket)
                    except Exception as close_exc:
                        self._record_publish_error(close_exc)
        if dead or filtered:
            with self.lock:
                self._filtered_messages += filtered
                for websocket in dead:
                    if websocket in self.connections:
                        self.connections.discard(websocket)
                        self._subscriptions.pop(websocket, None)
                        self._dropped_connections += 1

    def metrics(self) -> WebSocketHubMetrics:
        with self.lock:
            return WebSocketHubMetrics(
                active_connections=len(self.connections),
                backlog_size=len(self.recent_messages),
                max_backlog_size=int(self.recent_messages.maxlen or 0),
                dropped_connections=self._dropped_connections,
                published_messages=self._published_messages,
                publish_failures=self._publish_failures,
                last_error=self._last_error,
                send_timeout_sec=self._send_timeout_sec,
                coalesced_messages=self._coalesced_messages,
                filtered_messages=self._filtered_messages,
            )


EventBus = GatewayWebSocketHub
