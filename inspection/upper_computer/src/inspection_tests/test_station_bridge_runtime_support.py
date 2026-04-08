from __future__ import annotations

from types import SimpleNamespace

from station_bridge.reconnect_policy import ReconnectPolicy
from station_bridge.runtime_support import BridgeRuntimeSupport
from station_bridge.session_state import BridgeSession


class _Publisher:
    def __init__(self) -> None:
        self.messages = []

    def publish(self, msg) -> None:
        self.messages.append(msg)


class _Clock:
    class _Now:
        @staticmethod
        def to_msg():
            return None

    def now(self):
        return self._Now()


class _Watchdog:
    def __init__(self, *, expired: bool) -> None:
        self._expired = expired
        self.observed = 0

    def expired(self) -> bool:
        return self._expired

    def observe(self) -> None:
        self.observed += 1
        self._expired = False


class _Adapter:
    def __init__(self, *, fail_close: bool = False) -> None:
        self.fail_close = fail_close
        self.handshakes = []

    def close(self) -> None:
        if self.fail_close:
            raise RuntimeError('serial close failed')

    def query_capabilities(self, seq: int) -> None:
        self.handshakes.append(seq)


class _CommandTracker:
    def stale(self, *args, **kwargs):
        return []


class _CommandCenter:
    def __init__(self) -> None:
        self.tracker = _CommandTracker()

    def snapshot(self):
        return []

    def rollover_session(self, generation: int):
        return []


class _ResetSync:
    def snapshot(self):
        return {'pending': False}


class _NodeStub:
    def __init__(self, *, fail_close: bool = False, watchdog_expired: bool = False) -> None:
        self.item_id = 1
        self.batch_id = 'B1'
        self.trace_id = 'T1'
        self.event_pub = _Publisher()
        self.state_pub = _Publisher()
        self.fault_pub = _Publisher()
        self.command_center = _CommandCenter()
        self.capabilities = SimpleNamespace(to_dict=lambda: {'features': ['SORT_ACK']})
        self.session = BridgeSession(protocol_version=1)
        self.session.mark_ready(device_id='dev', capabilities={'features': ['SORT_ACK']})
        self.reset_sync = _ResetSync()
        self.watchdog = _Watchdog(expired=watchdog_expired)
        self.reconnect_policy = ReconnectPolicy(base_delay_sec=0.01, max_delay_sec=0.01)
        self.next_reconnect_at = 0.0
        self.lifecycle_state = 'ACTIVE'
        self.adapter = _Adapter(fail_close=fail_close)
        self.seq = 0

    def get_clock(self):
        return _Clock()

    def get_parameter(self, name: str):
        values = {'ack_stale_timeout_sec': 0.01}
        return SimpleNamespace(value=values[name])

    def is_active(self) -> bool:
        return True

    def _next_seq(self) -> int:
        value = self.seq
        self.seq += 1
        return value


def test_close_adapter_emits_failure_event() -> None:
    node = _NodeStub(fail_close=True)
    support = BridgeRuntimeSupport(node)

    ok, error = support.close_adapter()

    assert ok is False
    assert 'serial close failed' in error
    assert node.event_pub.messages


def test_watchdog_tick_marks_degraded_and_schedules_handshake() -> None:
    node = _NodeStub(watchdog_expired=True)
    support = BridgeRuntimeSupport(node)

    support.watchdog_tick()

    assert node.session.phase.value == 'DEGRADED'
    assert node.next_reconnect_at > 0.0
    assert node.state_pub.messages
