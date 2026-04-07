from __future__ import annotations

import time
from typing import Any

from inspection_interfaces.msg import CountStats

from .fsm_core import StationPhase


class FsmMetricsService:
    """Own phase timing and cycle statistics for the station FSM."""

    def __init__(self, node: Any) -> None:
        self.node = node

    def record_phase_duration(self, phase: StationPhase, elapsed: float) -> None:
        if phase in (StationPhase.BOOT, StationPhase.IDLE):
            return
        key = phase.value.lower()
        self.node.phase_timings_ms[key] = round(self.node.phase_timings_ms.get(key, 0.0) + elapsed * 1000.0, 3)

    def finish_cycle(self) -> None:
        self.node.stats['total'] += 1
        decision = (self.node.current_decision or 'NG').lower()
        if decision in self.node.stats:
            self.node.stats[decision] += 1
        cycle_elapsed = time.monotonic() - self.node.cycle_start if self.node.cycle_start is not None else 0.0
        self.node.stats['cycle_times'].append(cycle_elapsed)
        out = CountStats()
        out.stamp = self.node.get_clock().now().to_msg()
        out.total_count = int(self.node.stats['total'])
        out.ok_count = int(self.node.stats['ok'])
        out.ng_count = int(self.node.stats['ng'])
        out.recheck_count = int(self.node.stats['recheck'])
        out.yield_rate = float(self.node.stats['ok']) / float(max(1, self.node.stats['total']))
        out.avg_cycle_time_sec = float(sum(self.node.stats['cycle_times']) / max(1, len(self.node.stats['cycle_times'])))
        self.node.count_pub.publish(out)
        self.node.runtime.current.phase_timings_ms = dict(self.node.phase_timings_ms)
        self.node.runtime.current.retry_counts = dict(self.node.data.retry_counts)
        self.node.emit_event(
            'cycle_finish',
            decision=self.node.current_decision or 'NG',
            cycle_time_sec=round(cycle_elapsed, 4),
            phase_timings_ms=self.node.phase_timings_ms,
            result_detail=self.node.last_result_detail,
            cycle_index=self.node.data.cycle_index,
            retry_counts=self.node.data.retry_counts,
            runtime=self.node.runtime.current.snapshot(),
        )
        self.node.current_decision = None
        self.node.last_sort_cmd = None
        self.node.last_result_detail = {}
