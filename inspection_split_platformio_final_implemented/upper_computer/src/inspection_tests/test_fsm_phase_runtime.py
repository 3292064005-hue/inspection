from __future__ import annotations

import time
from types import SimpleNamespace

from inspection_fsm.fsm_core import FSMData, StationPhase
from inspection_fsm.phase_runtime import FSMPhaseRuntimeSupport


class _Param:
    def __init__(self, value):
        self.value = value


class _NodeStub:
    def __init__(self) -> None:
        self.data = FSMData(phase=StationPhase.FEED_WAIT_ACK)
        self.data.retry_counts = {}
        self.phase_start = time.monotonic() - 1.0
        self.last_sort_cmd = object()
        self.events: list[tuple[str, dict]] = []
        self.faults: list[tuple[str, str]] = []
        self.feed_requests = 0
        self.capture_requests = 0
        self.sort_requests = 0
        self.params = {
            'feed_retry_limit': 1,
            'capture_retry_limit': 1,
            'analyze_retry_limit': 1,
            'sort_retry_limit': 1,
            'feed_timeout_sec': 0.01,
            'capture_timeout_sec': 0.01,
            'capture_frame_timeout_sec': 0.01,
            'sort_timeout_sec': 0.01,
            'sort_done_timeout_sec': 0.01,
            'recovery_timeout_sec': 0.01,
            'auto_self_check_pass': False,
            'auto_recovery_pass': False,
        }
        self.runtime = SimpleNamespace(
            current=SimpleNamespace(bind=lambda **_: None, clear=lambda: None, snapshot=lambda: {}, current_phase='', phase_timings_ms={}, retry_counts={}),
            enter_manual=lambda: None,
            exit_manual=lambda: setattr(self, 'manual_exited', True),
            snapshot=lambda: {'mode': 'manual'},
        )
        self.current_decision = None
        self.last_result_detail = {}
        self.cycle_start = None
        self.phase_timings_ms = {}
        self.manual_exited = False

    def is_active(self) -> bool:
        return True

    def get_parameter(self, name: str):
        return _Param(self.params[name])

    def has_parameter(self, name: str) -> bool:
        return name in self.params

    def emit_event(self, name: str, **payload) -> None:
        self.events.append((name, payload))

    def publish_feed_request(self) -> None:
        self.feed_requests += 1

    def publish_capture_request(self) -> None:
        self.capture_requests += 1

    def publish_sort_request(self) -> None:
        self.sort_requests += 1

    def publish_reset_request(self) -> None:
        raise AssertionError('reset not expected')

    def finish_cycle(self) -> None:
        raise AssertionError('finish_cycle not expected')

    def raise_fault(self, code: str, description: str, event=None) -> None:
        self.faults.append((code, description))

    def apply_event(self, event, reason: str) -> None:
        self.events.append((f'apply:{event.value}', {'reason': reason}))


def test_tick_retries_once_then_raises_fault() -> None:
    node = _NodeStub()
    runtime = FSMPhaseRuntimeSupport(node)

    runtime.tick()
    assert node.feed_requests == 1
    assert node.data.retry_counts['feed_wait_ack'] == 1
    assert not node.faults

    node.phase_start = time.monotonic() - 1.0
    runtime.tick()
    assert node.faults[-1][0] == 'FAULT_FEED_WAIT_ACK_TIMEOUT'


def test_ready_phase_entry_exits_manual_before_auto_feed() -> None:
    node = _NodeStub()
    node.data.phase = StationPhase.READY
    node.data.manual_mode_enabled = False
    runtime = FSMPhaseRuntimeSupport(node)

    runtime.dispatch_phase_entry()

    assert node.manual_exited is True
    assert node.events[-1][0] == 'apply:FEED_REQUESTED'
