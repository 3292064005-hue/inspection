from __future__ import annotations

import asyncio

from inspection_hmi_gateway.ws_hub import GatewayWebSocketHub


def test_ws_hub_records_publish_failure_without_loop() -> None:
    hub = GatewayWebSocketHub(backlog_size=2)
    hub.broadcast('station.state', {'traceId': 'T-1'})
    metrics = hub.metrics()
    assert metrics.publish_failures == 1
    assert metrics.last_error
    assert metrics.published_messages == 0

class _SlowWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False
    async def send_json(self, message: dict) -> None:
        await asyncio.sleep(0.05)
        self.sent.append(message)
    async def close(self) -> None:
        self.closed = True

def test_ws_hub_drops_slow_connections_on_send_timeout() -> None:
    async def _run() -> None:
        hub = GatewayWebSocketHub(backlog_size=2, send_timeout_sec=0.001)
        websocket = _SlowWebSocket()
        await hub.connect(websocket)
        assert websocket in hub.connections
        await hub._broadcast_async(hub.make_message('station.state', {'traceId': 'T-2'}))
        metrics = hub.metrics()
        assert websocket.closed is True
        assert websocket not in hub.connections
        assert metrics.publish_failures >= 1
        assert metrics.dropped_connections >= 1
        assert metrics.send_timeout_sec == 0.001
    asyncio.run(_run())
