from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Callable, Literal

LifecycleState = Literal['UNCONFIGURED', 'INACTIVE', 'ACTIVE', 'FINALIZED', 'ERROR']
LifecycleTransition = Literal['CONFIGURE', 'ACTIVATE', 'DEACTIVATE', 'CLEANUP', 'SHUTDOWN']
TransitionHook = Callable[[str], tuple[bool, str] | bool | None]

_ALLOWED_TRANSITIONS: dict[str, dict[str, str]] = {
    'UNCONFIGURED': {'CONFIGURE': 'INACTIVE', 'SHUTDOWN': 'FINALIZED'},
    'INACTIVE': {'ACTIVATE': 'ACTIVE', 'CLEANUP': 'UNCONFIGURED', 'SHUTDOWN': 'FINALIZED'},
    'ACTIVE': {'DEACTIVATE': 'INACTIVE', 'SHUTDOWN': 'FINALIZED'},
    'ERROR': {'CLEANUP': 'UNCONFIGURED', 'SHUTDOWN': 'FINALIZED'},
    'FINALIZED': {},
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


@dataclass(slots=True)
class TransitionRecord:
    transition: str
    from_state: str
    to_state: str
    reason: str = ''
    success: bool = True
    message: str = ''
    at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            'transition': self.transition,
            'from_state': self.from_state,
            'to_state': self.to_state,
            'success': self.success,
            'at': self.at,
        }
        if self.reason:
            payload['reason'] = self.reason
        if self.message:
            payload['message'] = self.message
        return payload


@dataclass(slots=True)
class ManagedNodeRuntime:
    node_name: str
    state: LifecycleState = 'UNCONFIGURED'
    last_reason: str = ''
    last_message: str = ''
    transition_history: list[TransitionRecord] = field(default_factory=list)

    def can_transition(self, transition: str) -> bool:
        return transition in _ALLOWED_TRANSITIONS.get(self.state, {})

    def target_state(self, transition: str) -> str:
        return _ALLOWED_TRANSITIONS.get(self.state, {}).get(transition, self.state)

    def transition(self, transition: LifecycleTransition, *, reason: str = '', hook: TransitionHook | None = None) -> TransitionRecord:
        current = self.state
        if not self.can_transition(transition):
            record = TransitionRecord(
                transition=transition,
                from_state=current,
                to_state=current,
                reason=reason,
                success=False,
                message=f'invalid transition from {current}',
            )
            self.last_reason = reason
            self.last_message = record.message
            self._remember(record)
            return record

        message = ''
        success = True
        if hook is not None:
            try:
                result = hook(transition)
                if isinstance(result, tuple):
                    success = bool(result[0])
                    message = str(result[1]) if len(result) > 1 else ''
                elif isinstance(result, bool):
                    success = result
                elif result is None:
                    success = True
                else:
                    success = bool(result)
            except Exception as exc:  # pragma: no cover - defensive
                success = False
                message = str(exc)

        target: LifecycleState = self.target_state(transition) if success else 'ERROR'
        self.state = target
        self.last_reason = reason
        self.last_message = message
        record = TransitionRecord(
            transition=transition,
            from_state=current,
            to_state=target,
            reason=reason,
            success=success,
            message=message,
        )
        self._remember(record)
        return record

    def snapshot(self) -> dict[str, object]:
        return {
            'node': self.node_name,
            'lifecycle_state': self.state,
            'last_reason': self.last_reason,
            'last_message': self.last_message,
            'history': [item.to_dict() for item in self.transition_history[-10:]],
        }

    def _remember(self, record: TransitionRecord) -> None:
        self.transition_history.append(record)
        self.transition_history = self.transition_history[-50:]
