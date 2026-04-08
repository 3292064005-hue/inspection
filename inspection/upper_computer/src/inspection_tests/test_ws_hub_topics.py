from __future__ import annotations

import asyncio
from types import SimpleNamespace

from inspection_hmi_gateway.ws_hub import GatewayWebSocketHub


class _WebSocket:
    def __init__(self, topics: str = '') -> None:
        self.sent: list[dict] = []
        self.closed = False
        self.query_params = {'topics': topics}

    async def send_json(self, message: dict) -> None:
        self.sent.append(message)

    async def close(self) -> None:
        self.closed = True


def test_ws_hub_filters_topics_and_coalesces_backlog() -> None:
    async def _run() -> None:
        hub = GatewayWebSocketHub(backlog_size=4)
        ws = _WebSocket('station')
        await hub.connect(ws)
        await hub._broadcast_async(hub.make_message('system.heartbeat', {'source': 'ROS2'}))
        await hub._broadcast_async(hub.make_message('station.state.updated', {'batchId': 'B-1'}))
        await hub._broadcast_async(hub.make_message('station.state.updated', {'batchId': 'B-2'}))
        metrics = hub.metrics()
        assert all(item['topic'] == 'station' for item in ws.sent)
        hub.broadcast('station.state.updated', {'batchId': 'B-3'})
        hub.broadcast('station.state.updated', {'batchId': 'B-4'})
        assert metrics.filtered_messages >= 1

    asyncio.run(_run())
