from __future__ import annotations

"""Gateway runtime utilities.

``runtime_components`` remains the stable import surface for shared runtime
helpers, while heavier projection/artifact logic now lives in
``runtime_projection``.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event
from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default



def utc_now() -> str:
    """Return the current UTC time formatted for gateway payloads."""
    return datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')



def ros_time_to_iso(stamp: Any) -> str:
    """Convert a ROS builtin time-like object into an ISO8601 UTC string.

    Args:
        stamp: Any object exposing ``sec`` and ``nanosec`` attributes.

    Returns:
        ISO8601 timestamp string.
    """
    try:
        sec = int(getattr(stamp, 'sec', 0))
        nanosec = int(getattr(stamp, 'nanosec', 0))
        return datetime.fromtimestamp(sec + nanosec / 1_000_000_000, tz=UTC).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    except Exception:
        return utc_now()



def to_health(level: str) -> str:
    """Map a diagnostic severity into the HMI health vocabulary."""
    value = str(level).upper()
    if value in {'ERROR', 'STALE'}:
        return 'OFFLINE'
    if value in {'WARN', 'WARNING', 'DEGRADED'}:
        return 'DEGRADED'
    return 'ONLINE'



def normalize_phase(value: str) -> str:
    """Map raw station/FSM phases into the HMI phase model."""
    mapping = {
        'BOOT': 'BOOT',
        'SELF_CHECK': 'BOOT',
        'IDLE': 'IDLE',
        'READY': 'READY',
        'FEED_WAIT_ACK': 'FEEDING',
        'FEEDING': 'FEEDING',
        'POSITION_WAIT': 'POSITION_CHECK',
        'POSITION_READY': 'POSITION_CHECK',
        'CAPTURE_WAIT_FRAME': 'CAPTURE',
        'CAPTURE': 'CAPTURE',
        'ANALYZE_WAIT': 'ANALYZE',
        'ANALYZE': 'ANALYZE',
        'DECISION_WAIT': 'ANALYZE',
        'SORT_WAIT_ACK': 'SORTING',
        'SORT_WAIT_DONE': 'SORTING',
        'SORTING': 'SORTING',
        'COUNT_UPDATE': 'COUNT_UPDATE',
        'RECOVERING': 'FAULT',
        'FAULT': 'FAULT',
        'MANUAL_MODE': 'IDLE',
        'RESETTING': 'FAULT',
        'HEARTBEAT_LOST': 'FAULT',
    }
    return mapping.get(str(value).upper(), 'IDLE')



def normalize_mode(phase: str, detail: dict[str, Any] | None = None) -> str:
    """Map HMI phase and detail payload into the HMI mode vocabulary."""
    detail = detail or {}
    raw_mode = str(detail.get('mode', '')).upper()
    if phase == 'FAULT':
        return 'FAULT'
    if raw_mode in {'DEBUG', 'MANUAL'}:
        return 'DEBUG'
    if phase in {'FEEDING', 'POSITION_CHECK', 'CAPTURE', 'ANALYZE', 'SORTING', 'COUNT_UPDATE'}:
        return 'AUTO'
    return 'IDLE'


@dataclass(slots=True)
class ServiceCallResult:
    """Normalized ROS service invocation result.

    Attributes:
        ok: Whether the invocation completed successfully.
        message: Human-readable completion or failure message.
        payload: Optional raw ROS response object.
    """

    ok: bool
    message: str
    payload: Any | None = None


class RosServiceInvoker:
    """Invoke ROS services without busy-wait polling."""

    def __init__(self, *, wait_service_timeout_sec: float = 1.5, call_timeout_sec: float = 3.0) -> None:
        self.wait_service_timeout_sec = max(0.1, float(wait_service_timeout_sec))
        self.call_timeout_sec = max(0.1, float(call_timeout_sec))

    def call(
        self,
        client: Any,
        request: Any,
        *,
        service_name: str,
        unavailable_message: str,
        timeout_message: str,
    ) -> ServiceCallResult:
        """Invoke a ROS service client and wait for completion."""
        if not client.wait_for_service(timeout_sec=self.wait_service_timeout_sec):
            return ServiceCallResult(False, unavailable_message)
        try:
            future = client.call_async(request)
        except Exception as exc:
            return ServiceCallResult(False, f'{service_name} call failed: {exc}')
        done = Event()
        future.add_done_callback(lambda _future: done.set())
        if not done.wait(self.call_timeout_sec):
            return ServiceCallResult(False, timeout_message)
        try:
            response = future.result()
        except Exception as exc:
            return ServiceCallResult(False, f'{service_name} call failed: {exc}')
        if response is None:
            return ServiceCallResult(False, timeout_message)
        return ServiceCallResult(bool(getattr(response, 'success', False)), str(getattr(response, 'message', '')), response)


from .runtime_projection import GatewayArtifactResolver, GatewayReadModelProjector, PendingCorrelationStore

__all__ = [
    '_safe_float',
    '_safe_int',
    'GatewayArtifactResolver',
    'GatewayReadModelProjector',
    'PendingCorrelationStore',
    'RosServiceInvoker',
    'ServiceCallResult',
    'normalize_mode',
    'normalize_phase',
    'ros_time_to_iso',
    'to_health',
    'utc_now',
]
