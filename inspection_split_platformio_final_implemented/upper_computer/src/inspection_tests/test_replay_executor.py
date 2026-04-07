from pathlib import Path
import json

from inspection_logger.replay_executor import ReplayExecutor


def test_replay_executor_lists_and_loads_trace(tmp_path: Path):
    results = tmp_path / 'results'
    traces = tmp_path / 'traces'
    results.mkdir(parents=True)
    traces.mkdir(parents=True)
    (results / 'replay_manifest.jsonl').write_text(json.dumps({'trace_id': 'TRACE-1'}) + '\n', encoding='utf-8')
    (results / 'cycle_summary.jsonl').write_text(json.dumps({'trace_id': 'TRACE-1', 'final_status': 'COMPLETED', 'decision': 'OK', 'final_phase': 'COUNT_UPDATE'}) + '\n', encoding='utf-8')
    (traces / 'TRACE-1.jsonl').write_text(
        json.dumps({'type': 'capture_request'}) + '\n' +
        json.dumps({'type': 'inspection_result'}) + '\n' +
        json.dumps({'type': 'sort_command'}) + '\n' +
        json.dumps({'type': 'cycle_finish'}) + '\n', encoding='utf-8'
    )
    executor = ReplayExecutor(tmp_path)
    assert executor.list_traces() == ['TRACE-1']
    summary = executor.replay_summary('TRACE-1')
    assert summary['trace_id'] == 'TRACE-1'
    assert summary['event_count'] == 4
    assert summary['final_type'] == 'cycle_finish'
    assert summary['validation']['valid'] is True
    diff = executor.compare_trace_to_summary('TRACE-1')
    assert diff['trace_id'] == 'TRACE-1'
