from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

TRANSITION_NAME_TO_ID = {
    'CONFIGURE': 1,
    'CLEANUP': 2,
    'ACTIVATE': 3,
    'DEACTIVATE': 4,
    'SHUTDOWN': 5,
}
TRANSITION_ID_TO_NAME = {value: key for key, value in TRANSITION_NAME_TO_ID.items()}
STATE_NAME_TO_ID = {
    'UNKNOWN': 0,
    'UNCONFIGURED': 1,
    'INACTIVE': 2,
    'ACTIVE': 3,
    'FINALIZED': 4,
    'ERROR': 5,
}


def lifecycle_transition_name(*, transition_id: int | None = None, label: str | None = None) -> str:
    label_value = str(label or '').strip().upper()
    if label_value:
        if label_value == 'TRANSITION_CONFIGURE':
            return 'CONFIGURE'
        if label_value == 'TRANSITION_CLEANUP':
            return 'CLEANUP'
        if label_value == 'TRANSITION_ACTIVATE':
            return 'ACTIVATE'
        if label_value == 'TRANSITION_DEACTIVATE':
            return 'DEACTIVATE'
        if 'SHUTDOWN' in label_value:
            return 'SHUTDOWN'
        if label_value in TRANSITION_NAME_TO_ID:
            return label_value
    if transition_id is None:
        return ''
    return TRANSITION_ID_TO_NAME.get(int(transition_id), '')


def lifecycle_state_payload(state_name: str) -> tuple[int, str]:
    normalized = str(state_name or 'UNKNOWN').strip().upper() or 'UNKNOWN'
    return STATE_NAME_TO_ID.get(normalized, 0), normalized.lower()


@dataclass(slots=True)
class LifecycleBridgeAvailability:
    enabled: bool
    reason: str = ''
    services: tuple[str, ...] = ()


class LifecycleCompatibilityBridge:
    def __init__(self, *, node: Any, node_name: str, transition_handler: Callable[[str], dict[str, object]], snapshot_handler: Callable[[], dict[str, object]]) -> None:
        self.node = node
        self.node_name = node_name
        self.transition_handler = transition_handler
        self.snapshot_handler = snapshot_handler
        self.services: list[Any] = []
        self.availability = LifecycleBridgeAvailability(enabled=False, reason='lifecycle_msgs_unavailable')
        try:
            from lifecycle_msgs.msg import State  # noqa: F401
            from lifecycle_msgs.srv import ChangeState, GetState
        except Exception:
            return
        self._change_state_type = ChangeState
        self._get_state_type = GetState
        change_name = f'/{node_name}/change_state'
        state_name = f'/{node_name}/get_state'
        self.services.append(node.create_service(ChangeState, change_name, self._handle_change_state))
        self.services.append(node.create_service(GetState, state_name, self._handle_get_state))
        self.availability = LifecycleBridgeAvailability(enabled=True, services=(change_name, state_name))

    def _handle_change_state(self, request: Any, response: Any) -> Any:
        transition = getattr(request, 'transition', None)
        transition_name = lifecycle_transition_name(
            transition_id=getattr(transition, 'id', None),
            label=getattr(transition, 'label', ''),
        )
        if not transition_name:
            response.success = False
            return response
        try:
            record = self.transition_handler(transition_name, reason='native_lifecycle_service')
        except Exception:
            response.success = False
            return response
        response.success = bool(record.get('success', False))
        return response

    def _handle_get_state(self, _request: Any, response: Any) -> Any:
        snapshot = self.snapshot_handler()
        state_id, state_label = lifecycle_state_payload(str(snapshot.get('lifecycle_state', 'UNKNOWN')))
        current_state = getattr(response, 'current_state', None)
        if current_state is None:
            return response
        current_state.id = int(state_id)
        current_state.label = str(state_label)
        return response
