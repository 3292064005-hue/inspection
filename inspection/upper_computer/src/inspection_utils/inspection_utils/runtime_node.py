from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

try:  # pragma: no cover - depends on ROS runtime
    from rclpy.node import Node as _StandardNodeBase
except Exception:  # pragma: no cover
    class _StandardNodeBase:  # type: ignore
        pass

try:  # pragma: no cover - depends on ROS runtime
    from rclpy.lifecycle import LifecycleNode as _LifecycleNodeBase
    NATIVE_LIFECYCLE_AVAILABLE = True
except Exception:  # pragma: no cover
    _LifecycleNodeBase = _StandardNodeBase  # type: ignore[assignment]
    NATIVE_LIFECYCLE_AVAILABLE = False

_CALLBACK_TO_TRANSITION = {
    'on_configure': 'CONFIGURE',
    'on_activate': 'ACTIVATE',
    'on_deactivate': 'DEACTIVATE',
    'on_cleanup': 'CLEANUP',
    'on_shutdown': 'SHUTDOWN',
}


class StandardRuntimeNode(_StandardNodeBase):
    """Standard non-lifecycle runtime base.

    Nodes that must remain outside ROS 2 lifecycle governance should inherit
    this base instead of :class:`InspectionRuntimeNode`. The class intentionally
    adds no lifecycle subscriptions, native lifecycle services, or compatibility
    bridges so runtime-topology declarations stay aligned with the executable's
    actual control surface.
    """


class InspectionRuntimeNode(_LifecycleNodeBase):
    """Runtime base node.

    When the ROS 2 lifecycle API is available, this base class becomes a real
    ``LifecycleNode``. In lighter test environments it gracefully falls back to
    a standard ``Node`` so syntax-only and pure Python validation can continue
    to run without ROS message generation.

    The class also wraps subclass lifecycle callbacks so native lifecycle
    transitions and the managed-runtime state machine remain synchronized.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        for callback_name, transition in _CALLBACK_TO_TRANSITION.items():
            callback = cls.__dict__.get(callback_name)
            if callback is None or getattr(callback, '_inspection_runtime_wrapped', False):
                continue

            @wraps(callback)
            def _wrapped(self, *args: Any, __callback: Callable[..., Any] = callback, __transition: str = transition, **kw: Any) -> Any:
                result = __callback(self, *args, **kw)
                sync = getattr(self, '_sync_native_lifecycle_callback', None)
                if callable(sync):
                    sync(__transition, result)
                return result

            setattr(_wrapped, '_inspection_runtime_wrapped', True)
            setattr(cls, callback_name, _wrapped)

    def _sync_native_lifecycle_callback(self, transition: str, callback_result: Any) -> None:
        if getattr(self, '_managed_transition_hook_active', False):
            return
        lifecycle_runtime = getattr(self, 'lifecycle_runtime', None)
        if lifecycle_runtime is None:
            return

        success = True
        message = ''
        if isinstance(callback_result, tuple):
            success = bool(callback_result[0])
            message = str(callback_result[1]) if len(callback_result) > 1 else ''
        elif isinstance(callback_result, bool):
            success = bool(callback_result)
        elif callback_result is None:
            success = True
        else:
            success = bool(callback_result)

        reason = str(getattr(self, '_native_transition_reason', '') or 'native_callback')
        record = lifecycle_runtime.transition(
            transition,
            reason=reason,
            hook=(lambda _transition: (success, message)),
        )
        publisher = getattr(self, '_publish_lifecycle_state', None)
        if callable(publisher):
            publisher(
                'native_lifecycle_transition',
                reason=reason,
                transition=transition,
                success=record.success,
                message=record.message,
            )


@dataclass(frozen=True, slots=True)
class RuntimeNodeCapabilities:
    native_lifecycle: bool
    base_type: str

    def to_dict(self) -> dict[str, object]:
        return {
            'nativeLifecycle': self.native_lifecycle,
            'baseType': self.base_type,
        }


def runtime_node_capabilities() -> RuntimeNodeCapabilities:
    return RuntimeNodeCapabilities(
        native_lifecycle=bool(NATIVE_LIFECYCLE_AVAILABLE),
        base_type='LifecycleNode' if NATIVE_LIFECYCLE_AVAILABLE else 'Node',
    )
