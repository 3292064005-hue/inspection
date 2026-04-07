from pathlib import Path
import json

from inspection_logger.benchmark_writer import BenchmarkWriter


def test_benchmark_writer_appends_summary(tmp_path: Path):
    writer = BenchmarkWriter(tmp_path)
    (tmp_path / 'results').mkdir(parents=True, exist_ok=True)
    writer.append_summary({'trace_id': 'TRACE-1', 'cycle_time_sec': 1.2, 'final_status': 'COMPLETED', 'decision': 'OK'})
    lines = (tmp_path / 'results' / 'benchmark.jsonl').read_text(encoding='utf-8').splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record['trace_id'] == 'TRACE-1'
    assert record['mean_cycle_time_sec'] == 1.2
