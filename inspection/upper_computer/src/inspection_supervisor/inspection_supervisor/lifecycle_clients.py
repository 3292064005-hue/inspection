from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ACTION_TO_TRANSITION = {
    'configure_node': 'CONFIGURE',
    'activate_node': 'ACTIVATE',
    'deactivate_node': 'DEACTIVATE',
    'cleanup_node': 'CLEANUP',
    'shutdown_node': 'SHUTDOWN',
}

TRANSITION_TO_TARGET = {
    'CONFIGURE': 'INACTIVE',
    'ACTIVATE': 'ACTIVE',
    'DEACTIVATE': 'INACTIVE',
    'CLEANUP': 'UNCONFIGURED',
    'SHUTDOWN': 'FINALIZED',
}


@dataclass(slots=True)
class LifecycleCommand:
    node: str
    transition: str
    target_state: str
    reason: str = ''
    stage: str = ''

    @property
    def signature(self) -> str:
        return f'{self.node}:{self.transition}:{self.target_state}'

    def to_dict(self) -> dict[str, Any]:
        payload = {
            'command': 'lifecycle_transition',
            'node': self.node,
            'transition': self.transition,
            'target_state': self.target_state,
            'signature': self.signature,
        }
        if self.reason:
            payload['reason'] = self.reason
        if self.stage:
            payload['stage'] = self.stage
        return payload



def lifecycle_command_from_plan_item(item: dict[str, Any]) -> LifecycleCommand | None:
    action = str(item.get('action', ''))
    node = str(item.get('node', ''))
    if not node or action not in ACTION_TO_TRANSITION:
        return None
    transition = ACTION_TO_TRANSITION[action]
    return LifecycleCommand(
        node=node,
        transition=transition,
        target_state=TRANSITION_TO_TARGET[transition],
        reason=str(item.get('reason', '')),
        stage=str(item.get('stage', '')),
    )
