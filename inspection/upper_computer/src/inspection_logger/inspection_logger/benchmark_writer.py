from __future__ import annotations

from pathlib import Path
from statistics import mean

from inspection_utils.logging_common import append_jsonl, utc_now_str


class BenchmarkWriter:
    def __init__(self, root: Path) -> None:
        self.path = root / 'results' / 'benchmark.jsonl'
        self._cycle_times: list[float] = []

    def append_summary(self, summary: dict) -> None:
        cycle_time = float(summary.get('cycle_time_sec', 0.0))
        self._cycle_times.append(cycle_time)
        record = {
            'time': utc_now_str(),
            'type': 'cycle_benchmark',
            'trace_id': summary.get('trace_id', ''),
            'cycle_time_sec': cycle_time,
            'final_status': summary.get('final_status', ''),
            'decision': summary.get('decision', ''),
            'mean_cycle_time_sec': round(mean(self._cycle_times), 6),
            'sample_count': len(self._cycle_times),
        }
        append_jsonl(self.path, record)
