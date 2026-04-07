from __future__ import annotations

import time
from typing import Any

from inspection_utils.param_parsing import parameter_as_bool

from .fsm_core import StationEvent, StationPhase, clear_cycle_runtime, finish_cycle, phase_timeout_key, start_cycle


class FSMPhaseRuntimeSupport:
    """Own phase-entry side effects, retry policy, and timeout handling for the station FSM."""

    def __init__(self, node: Any) -> None:
        self.node = node

    def run_command(self, command: str) -> None:
        if command == 'start_cycle':
            start_cycle(self.node.data)
            self.node.runtime.current.bind(
                cycle_index=self.node.data.cycle_index,
                trace_id=self.node.data.trace_id,
                item_id=self.node.data.item_id,
                batch_id=self.node.data.batch_id,
            )
            self.node.runtime.current.current_phase = self.node.data.phase.value
            self.node.cycle_start = time.monotonic()
            self.node.phase_timings_ms = {}
            self.node.emit_event('cycle_started', runtime=self.node.runtime.current.snapshot())
        elif command == 'finish_cycle':
            self.node.finish_cycle()
            finish_cycle(self.node.data)
            self.node.runtime.current.clear()
        elif command == 'clear_cycle':
            clear_cycle_runtime(self.node.data)
            self.node.current_decision = None
            self.node.last_sort_cmd = None
            self.node.last_result_detail = {}
            self.node.runtime.current.clear()
            self.node.cycle_start = None
        elif command == 'publish_feed':
            self.node.publish_feed_request()
        elif command == 'publish_capture':
            self.node.publish_capture_request()
        elif command == 'publish_sort':
            self.node.publish_sort_request()
        elif command == 'publish_reset':
            self.node.publish_reset_request()

    def dispatch_phase_entry(self) -> None:
        if self.node.data.phase == StationPhase.SELF_CHECK:
            self.node.emit_event('self_check_started')
            if parameter_as_bool(self.node, 'auto_self_check_pass', default=False):
                self.node.apply_event(StationEvent.SELF_CHECK_OK, 'auto_self_check_pass')
        elif self.node.data.phase == StationPhase.RECOVERING:
            self.node.emit_event('recovery_started', fault_code=self.node.data.last_fault_code)
            if parameter_as_bool(self.node, 'auto_recovery_pass', default=False):
                self.node.apply_event(StationEvent.RECOVERY_OK, 'auto_recovery_pass')
        elif self.node.data.phase == StationPhase.READY:
            self.node.runtime.exit_manual()
            if not self.node.data.manual_mode_enabled:
                self.node.apply_event(StationEvent.FEED_REQUESTED, 'auto_feed')
        elif self.node.data.phase == StationPhase.COUNT_UPDATE:
            self.node.apply_event(StationEvent.START, 'next_cycle')
        elif self.node.data.phase == StationPhase.MANUAL_MODE:
            self.node.runtime.enter_manual()
            self.node.emit_event('manual_mode_ready', runtime=self.node.runtime.snapshot())

    def retry_limit_for_phase(self, phase: StationPhase) -> int:
        mapping = {
            StationPhase.FEED_WAIT_ACK: int(self.node.get_parameter('feed_retry_limit').value),
            StationPhase.CAPTURE_WAIT_FRAME: int(self.node.get_parameter('capture_retry_limit').value),
            StationPhase.ANALYZE_WAIT: int(self.node.get_parameter('analyze_retry_limit').value),
            StationPhase.SORT_WAIT_ACK: int(self.node.get_parameter('sort_retry_limit').value),
            StationPhase.SORT_WAIT_DONE: int(self.node.get_parameter('sort_retry_limit').value),
        }
        return mapping.get(phase, 0)

    def retry_current_phase(self) -> bool:
        phase = self.node.data.phase
        limit = self.retry_limit_for_phase(phase)
        key = phase.value.lower()
        current = int(self.node.data.retry_counts.get(key, 0))
        if current >= limit:
            return False
        self.node.data.retry_counts[key] = current + 1
        self.node.phase_start = time.monotonic()
        if phase == StationPhase.FEED_WAIT_ACK:
            self.node.publish_feed_request()
        elif phase in (StationPhase.CAPTURE_WAIT_FRAME, StationPhase.ANALYZE_WAIT):
            self.node.publish_capture_request()
        elif phase in (StationPhase.SORT_WAIT_ACK, StationPhase.SORT_WAIT_DONE) and self.node.last_sort_cmd is not None:
            self.node.publish_sort_request()
        else:
            return False
        self.node.emit_event('phase_retry', retry_phase=phase.value, retry_index=self.node.data.retry_counts[key])
        return True

    def tick(self) -> None:
        if not self.node.is_active():
            return
        timeout_key = phase_timeout_key(self.node.data.phase)
        if not timeout_key:
            return
        if timeout_key == 'capture_frame_timeout_sec' and not self.node.has_parameter(timeout_key):
            timeout_key = 'capture_timeout_sec'
        if timeout_key == 'sort_done_timeout_sec' and not self.node.has_parameter(timeout_key):
            timeout_key = 'sort_timeout_sec'
        elapsed = time.monotonic() - self.node.phase_start
        if elapsed <= float(self.node.get_parameter(timeout_key).value):
            return
        if self.node.data.phase == StationPhase.RECOVERING:
            self.node.raise_fault('FAULT_RECOVERY_TIMEOUT', f'recovery timeout after {elapsed:.2f}s')
            return
        if self.retry_current_phase():
            return
        self.node.raise_fault(f'FAULT_{self.node.data.phase.value}_TIMEOUT', f'{self.node.data.phase.value} timeout after {elapsed:.2f}s')
