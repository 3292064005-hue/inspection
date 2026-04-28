from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from inspection_utils.lifecycle_common import allows_lifecycle_fallback, normalize_governed_node_name, requires_native_lifecycle

from .lifecycle_clients import LifecycleCommand

TRANSITION_TO_ID = {
    'CONFIGURE': 1,
    'CLEANUP': 2,
    'ACTIVATE': 3,
    'DEACTIVATE': 4,
    'SHUTDOWN': 5,
}

VALID_TRANSITIONS = frozenset(TRANSITION_TO_ID)


@dataclass(slots=True)
class NativeLifecycleDispatcher:
    node: Any
    timeout_sec: float = 0.15
    enabled: bool = field(init=False)
    _clients: dict[str, Any] = field(default_factory=dict)
    _transition_type: Any | None = field(init=False, default=None)
    _change_state_type: Any | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        try:
            from lifecycle_msgs.msg import Transition
            from lifecycle_msgs.srv import ChangeState
        except Exception:
            self.enabled = False
            self._transition_type = None
            self._change_state_type = None
            return
        self.enabled = True
        self._transition_type = Transition
        self._change_state_type = ChangeState

    def dispatch(self, command: LifecycleCommand, *, fallback: Callable[[dict[str, object]], None]) -> dict[str, object]:
        node_name = normalize_governed_node_name(command.node)
        transition_name = str(command.transition or '').strip().upper()
        if not node_name:
            return {'mode': 'rejected', 'service': '', 'queued': False, 'reason': 'node_required'}
        if transition_name not in VALID_TRANSITIONS:
            return self._fallback_or_reject(command, fallback=fallback, service='', reason='unsupported_transition')
        if not self.enabled or self._change_state_type is None or self._transition_type is None:
            return self._fallback_or_reject(command, fallback=fallback, service='', reason='native_lifecycle_unavailable')
        service_name = f'/{node_name}/change_state'
        client = self._clients.get(service_name)
        if client is None:
            client = self.node.create_client(self._change_state_type, service_name)
            self._clients[service_name] = client
        try:
            ready = bool(client.wait_for_service(timeout_sec=float(self.timeout_sec)))
        except Exception:
            ready = False
        if not ready:
            return self._fallback_or_reject(command, fallback=fallback, service=service_name, reason='service_unavailable')
        request = self._change_state_type.Request()
        request.transition.id = int(TRANSITION_TO_ID[transition_name])
        request.transition.label = str(transition_name.lower())
        try:
            future = client.call_async(request)
            future.add_done_callback(lambda fut: self._on_future(command, fut))
            return {'mode': 'native_service', 'service': service_name, 'queued': True, 'reason': ''}
        except Exception:
            return self._fallback_or_reject(command, fallback=fallback, service=service_name, reason='call_async_failed')

    def _fallback_or_reject(self, command: LifecycleCommand, *, fallback: Callable[[dict[str, object]], None], service: str, reason: str) -> dict[str, object]:
        normalized_node = normalize_governed_node_name(command.node)
        if requires_native_lifecycle(normalized_node):
            return {'mode': 'rejected_native_required', 'service': service, 'queued': False, 'reason': reason}
        if allows_lifecycle_fallback(normalized_node):
            fallback(command.to_dict())
            return {'mode': 'topic_fallback', 'service': service, 'queued': False, 'reason': reason}
        return {'mode': 'rejected', 'service': service, 'queued': False, 'reason': reason}

    def _on_future(self, command: LifecycleCommand, future: Any) -> None:
        try:
            result = future.result()
            success = bool(getattr(result, 'success', False))
            logger = self.node.get_logger()
            if success and hasattr(logger, 'info'):
                logger.info(f'lifecycle dispatch {command.signature} success=True')
            elif hasattr(logger, 'warning'):
                logger.warning(f'lifecycle dispatch {command.signature} success=False')
        except Exception:
            try:
                self.node.get_logger().warning(f'lifecycle dispatch failed for {command.signature}')
            except Exception:
                pass
