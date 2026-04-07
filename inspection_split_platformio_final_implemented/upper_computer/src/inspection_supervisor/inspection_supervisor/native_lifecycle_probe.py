from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LifecycleServiceAvailability:
    enabled: bool
    reason: str = ''


class NativeLifecycleProbe:
    """Query native ROS lifecycle state/transition services when available."""

    def __init__(self, node: Any, *, timeout_sec: float = 0.2) -> None:
        self.node = node
        self.timeout_sec = float(timeout_sec)
        self._state_clients: dict[str, Any] = {}
        self._transition_clients: dict[str, Any] = {}
        try:
            from lifecycle_msgs.srv import GetState, GetAvailableTransitions
        except Exception:
            self.enabled = False
            self.reason = 'lifecycle_msgs_unavailable'
            self._get_state_type = None
            self._get_transitions_type = None
            return
        self.enabled = True
        self.reason = ''
        self._get_state_type = GetState
        self._get_transitions_type = GetAvailableTransitions

    def availability(self) -> LifecycleServiceAvailability:
        return LifecycleServiceAvailability(enabled=self.enabled, reason=self.reason)

    def _client(self, node_name: str, *, service: str) -> Any | None:
        node_name = str(node_name or '').strip()
        if not node_name or not self.enabled:
            return None
        if service == 'state':
            service_name = f'/{node_name}/get_state'
            client = self._state_clients.get(service_name)
            if client is None:
                client = self.node.create_client(self._get_state_type, service_name)
                self._state_clients[service_name] = client
            return client
        service_name = f'/{node_name}/get_available_transitions'
        client = self._transition_clients.get(service_name)
        if client is None:
            client = self.node.create_client(self._get_transitions_type, service_name)
            self._transition_clients[service_name] = client
        return client

    def _call(self, client: Any) -> Any | None:
        if client is None:
            return None
        try:
            ready = bool(client.wait_for_service(timeout_sec=self.timeout_sec))
        except Exception:
            ready = False
        if not ready:
            return None
        request = client.srv_type.Request() if hasattr(client, 'srv_type') else client.request_type.Request()  # pragma: no cover
        try:
            future = client.call_async(request)
        except Exception:
            return None
        deadline = time.monotonic() + self.timeout_sec
        while time.monotonic() < deadline:
            if future.done():
                try:
                    return future.result()
                except Exception:
                    return None
            time.sleep(0.01)
        return None

    def get_state(self, node_name: str) -> str:
        client = self._client(node_name, service='state')
        result = self._call(client)
        if result is None:
            return ''
        current_state = getattr(result, 'current_state', None)
        label = getattr(current_state, 'label', '')
        return str(label or '').upper()

    def get_available_transitions(self, node_name: str) -> list[str]:
        client = self._client(node_name, service='transitions')
        result = self._call(client)
        if result is None:
            return []
        transitions = []
        for item in getattr(result, 'available_transitions', []) or []:
            transitions.append(str(getattr(item, 'label', '') or '').upper())
        return [item for item in transitions if item]


    def describe_nodes(self, node_names: list[str]) -> dict[str, dict[str, object]]:
        payload: dict[str, dict[str, object]] = {}
        for node_name in node_names:
            normalized = str(node_name or '').strip()
            if not normalized:
                continue
            payload[normalized] = {
                'state': self.get_state(normalized),
                'availableTransitions': self.get_available_transitions(normalized),
            }
        return payload

    def wait_for_state(self, node_name: str, target_state: str, *, timeout_sec: float = 3.0) -> bool:
        target = str(target_state or '').upper()
        deadline = time.monotonic() + float(timeout_sec)
        while time.monotonic() < deadline:
            if self.get_state(node_name) == target:
                return True
            time.sleep(0.05)
        return False
