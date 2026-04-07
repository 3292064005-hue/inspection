from pathlib import Path

from inspection_logger.trace_store import TraceStore


def test_trace_store_writes_run_artifacts_to_manifest(tmp_path: Path):
    store = TraceStore(tmp_path)
    store.set_run_artifacts(bag_recording={'enabled': True, 'output_path': 'bags/run'})
    store.append_summary({'trace_id': 'T1', 'final_status': 'COMPLETED', 'final_phase': 'READY'})
    manifest = (tmp_path / 'results' / 'replay_manifest.jsonl').read_text(encoding='utf-8')
    assert 'bags/run' in manifest
