from pathlib import Path
import json

from inspection_logger.regression_reporter import build_regression_report
from inspection_logger.regression_runner import RegressionRunner


def test_regression_runner_and_report(tmp_path: Path):
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
    cases = RegressionRunner(tmp_path).run()
    report = build_regression_report(cases)
    assert report['total'] == 1
    assert report['changed'] in {0, 1}
    assert report['results'][0]['trace_id'] == 'TRACE-1'
