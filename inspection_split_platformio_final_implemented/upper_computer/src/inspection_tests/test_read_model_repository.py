from __future__ import annotations

import json
from pathlib import Path

from inspection_hmi_gateway.read_model_policy import ReadModelPolicy
from inspection_hmi_gateway.read_model_repository import ReadModelRepository, ReadModelSyncRequiredError


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def test_read_model_repository_materializes_results_and_traces(tmp_path: Path) -> None:
    root = tmp_path / 'runtime'
    results = root / 'results'
    traces = root / 'traces'
    results.mkdir(parents=True)
    traces.mkdir(parents=True)
    (results / 'result_log.csv').write_text(
        'time,trace_id,batch_id,item_id,recipe_id,category,defect_type,score,qr_ok,qr_text,orientation_ok,color_name,color_ratio,image_path,annotated_image_path,detail_json\n'
        '2026-04-01T12:00:00Z,TRACE-001,B1,1,recipe_a,OK,NONE,0.99,1,QR1,1,red,0.95,images/raw.png,images/ann.png,"{""trace_id"": ""TRACE-001"", ""processing_ms"": 12.0}"\n',
        encoding='utf-8',
    )
    _write_jsonl(results / 'cycle_summary.jsonl', [{'trace_id': 'TRACE-001', 'decision': 'OK', 'cycle_time_sec': 0.032, 'image_paths': {'raw': 'images/raw.png', 'annotated': 'images/ann.png'}}])
    _write_jsonl(results / 'replay_manifest.jsonl', [{'trace_id': 'TRACE-001', 'run_artifacts': {'bag': 'bags/run.mcap'}, 'config_snapshot': {'recipe_path': 'config/recipe.yaml'}, 'artifacts': [{'kind': 'raw', 'path': 'images/raw.png'}]}])
    _write_jsonl(results / 'artifact_index.jsonl', [{'trace_id': 'TRACE-001', 'batch_id': 'B1', 'item_id': 1, 'kind': 'annotated', 'path': 'images/ann.png'}])
    _write_jsonl(traces / 'TRACE-001.jsonl', [{'type': 'fsm_transition', 'phase': 'READY'}])

    repository = ReadModelRepository(root)
    results_payload = repository.list_results()
    assert len(results_payload) == 1
    assert results_payload[0]['traceId'] == 'TRACE-001'
    detail = repository.get_result('TRACE-001')
    assert detail is not None
    assert detail['traceBundle']['artifactCount'] >= 2
    assert detail['traceBundle']['eventCount'] == 1


def test_read_model_repository_requires_explicit_repair_when_runtime_repair_disabled(tmp_path: Path) -> None:
    root = tmp_path / 'runtime'
    results = root / 'results'
    results.mkdir(parents=True, exist_ok=True)
    (results / 'result_log.csv').write_text('time,trace_id,batch_id,item_id,recipe_id,category,defect_type,score,qr_ok,qr_text,orientation_ok,color_name,color_ratio,image_path,annotated_image_path,detail_json\n', encoding='utf-8')
    repository = ReadModelRepository(root, policy=ReadModelPolicy(mode='hot', bootstrap_repair_on_empty_db=False, allow_runtime_repair_on_sync_mismatch=False, fallback_legacy_reads=False))
    try:
        repository.refresh_if_needed()
    except ReadModelSyncRequiredError:
        return
    raise AssertionError('stale or empty projections must require explicit repair when runtime repair is disabled')


def test_read_model_repository_can_disable_query_side_trace_refresh(tmp_path: Path) -> None:
    root = tmp_path / 'runtime'
    results = root / 'results'
    traces = root / 'traces'
    results.mkdir(parents=True)
    traces.mkdir(parents=True)
    (results / 'result_log.csv').write_text(
        'time,trace_id,batch_id,item_id,recipe_id,category,defect_type,score,qr_ok,qr_text,orientation_ok,color_name,color_ratio,image_path,annotated_image_path,detail_json\n'
        '2026-04-01T12:00:00Z,TRACE-002,B2,2,recipe_b,OK,NONE,0.99,1,QR2,1,red,0.95,images/raw.png,images/ann.png,"{""trace_id"": ""TRACE-002""}"\n',
        encoding='utf-8',
    )
    _write_jsonl(results / 'cycle_summary.jsonl', [{'trace_id': 'TRACE-002', 'decision': 'OK', 'cycle_time_sec': 0.032}])
    _write_jsonl(results / 'replay_manifest.jsonl', [])
    _write_jsonl(results / 'artifact_index.jsonl', [])
    _write_jsonl(traces / 'TRACE-002.jsonl', [{'type': 'fsm_transition', 'phase': 'READY'}])

    repository = ReadModelRepository(root, policy=ReadModelPolicy(mode='hot', bootstrap_repair_on_empty_db=True, allow_runtime_repair_on_sync_mismatch=False, fallback_legacy_reads=True, query_side_trace_refresh='disabled'))
    first = repository.get_result('TRACE-002')
    assert first is not None
    assert int(first['traceBundle']['eventCount']) == 1
    _write_jsonl(traces / 'TRACE-002.jsonl', [{'type': 'fsm_transition', 'phase': 'READY'}, {'type': 'inspection_result'}])
    second = repository.get_result('TRACE-002')
    assert second is not None
    assert int(second['traceBundle']['eventCount']) == 1


def test_read_model_repository_rebuild_repopulates_result_source(tmp_path: Path) -> None:
    root = tmp_path / 'runtime'
    results = root / 'results'
    traces = root / 'traces'
    results.mkdir(parents=True)
    traces.mkdir(parents=True)
    (results / 'result_log.csv').write_text(
        'time,trace_id,batch_id,item_id,recipe_id,category,defect_type,score,qr_ok,qr_text,orientation_ok,color_name,color_ratio,image_path,annotated_image_path,detail_json\n'
        '2026-04-01T12:00:00Z,TRACE-REBUILD,B3,3,recipe_c,OK,NONE,0.95,1,QR3,1,green,0.75,images/raw.png,images/ann.png,"{""trace_id"": ""TRACE-REBUILD""}"\n',
        encoding='utf-8',
    )
    _write_jsonl(results / 'cycle_summary.jsonl', [{'trace_id': 'TRACE-REBUILD', 'decision': 'OK', 'cycle_time_sec': 0.010}])
    _write_jsonl(results / 'replay_manifest.jsonl', [])
    _write_jsonl(results / 'artifact_index.jsonl', [])
    _write_jsonl(traces / 'TRACE-REBUILD.jsonl', [{'type': 'fsm_transition', 'phase': 'READY'}])

    repository = ReadModelRepository(root)
    repository.repair()

    with repository.connection() as conn:
        row = conn.execute('SELECT COUNT(*) AS count FROM result_source WHERE trace_id=?', ('TRACE-REBUILD',)).fetchone()
    assert row is not None
    assert int(row['count']) == 1
