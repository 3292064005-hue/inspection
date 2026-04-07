from __future__ import annotations

import csv
import json
from pathlib import Path

from inspection_hmi_gateway.result_store import ResultStore
from inspection_hmi_gateway.read_model_policy import ReadModelPolicy


def _prepare_logs(root: Path) -> None:
    results_dir = root / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    with (results_dir / 'result_log.csv').open('w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['time', 'trace_id', 'batch_id', 'item_id', 'recipe_id', 'category', 'defect_type', 'score', 'qr_ok', 'qr_text', 'orientation_ok', 'color_name', 'color_ratio', 'image_path', 'annotated_image_path', 'detail_json'])
        writer.writerow(['2026-03-31T08:00:00Z', 'trace-1', 'BATCH-1', 1, 'recipe-a', 'COLOR', 'RED_SHIFT', 0.91, True, 'QR001', True, 'red', 0.8, 'images/raw-1.png', 'images/ann-1.png', json.dumps({'warnings': ['色偏'], 'processing_ms': 12.5}, ensure_ascii=False)])
        writer.writerow(['2026-03-31T08:01:00Z', 'trace-2', 'BATCH-2', 2, 'recipe-b', 'QR', 'NONE', 0.45, False, 'QR002', True, 'red', 0.8, 'images/raw-2.png', 'images/ann-2.png', json.dumps({'processing_ms': 20.0}, ensure_ascii=False)])
    with (results_dir / 'cycle_summary.jsonl').open('w', encoding='utf-8') as fh:
        fh.write(json.dumps({'trace_id': 'trace-1', 'decision': 'NG', 'cycle_time_sec': 0.123, 'phase_timings_ms': {'feeding': 10, 'capture': 20, 'analyze': 30, 'sorting': 40}, 'image_paths': {'raw': 'images/raw-1.png', 'annotated': 'images/ann-1.png'}}, ensure_ascii=False) + '\n')
        fh.write(json.dumps({'trace_id': 'trace-2', 'decision': 'OK', 'cycle_time_sec': 0.222, 'phase_timings_ms': {'feeding': 11, 'capture': 22, 'analyze': 33, 'sorting': 44}}, ensure_ascii=False) + '\n')
    with (results_dir / 'replay_manifest.jsonl').open('w', encoding='utf-8') as fh:
        fh.write(json.dumps({'trace_id': 'trace-1', 'trace_path': str(root / 'traces' / 'trace-1.jsonl'), 'summary': {'trace_id': 'trace-1'}, 'run_artifacts': {'bag_recording': {'enabled': False}}}, ensure_ascii=False) + '\n')


def test_query_results_filters_and_summary(tmp_path: Path) -> None:
    _prepare_logs(tmp_path)
    store = ResultStore(tmp_path)

    all_items = store.list_results()
    assert len(all_items) == 2
    filtered = store.query_results(batch_id='BATCH-1', decision='NG')
    assert len(filtered) == 1
    assert filtered[0]['traceId'] == 'trace-1'
    assert filtered[0]['itemId'] == 1
    summary = store.batch_summary(batch_id='BATCH-1')
    assert summary['total'] == 1
    assert summary['ng'] == 1
    assert summary['yieldRate'] == 0.0


def test_get_result_includes_trace_bundle(tmp_path: Path) -> None:
    _prepare_logs(tmp_path)
    (tmp_path / 'traces').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'traces' / 'trace-1.jsonl').write_text(json.dumps({'type': 'cycle_finish', 'trace_id': 'trace-1'}, ensure_ascii=False) + '\n', encoding='utf-8')
    store = ResultStore(tmp_path)
    detail = store.get_result('trace-1')
    assert detail is not None
    assert detail['traceId'] == 'trace-1'
    assert detail['itemId'] == 1
    assert detail['artifactCount'] >= 2
    assert detail['traceBundle']['eventCount'] == 1


def test_result_store_refreshes_when_trace_files_change(tmp_path: Path) -> None:
    runtime = tmp_path / 'runtime'
    results = runtime / 'results'
    traces = runtime / 'traces'
    results.mkdir(parents=True, exist_ok=True)
    traces.mkdir(parents=True, exist_ok=True)
    (results / 'result_log.csv').write_text(
        'time,batch_id,item_id,trace_id,recipe_id,category,defect_type,score,image_path,annotated_image_path,detail_json,qr_text\n'
        '2026-01-01T00:00:00,b1,1,t1,r1,OK,NONE,0.99,results/raw.png,results/annotated.png,{},QR1\n',
        encoding='utf-8',
    )
    (results / 'cycle_summary.jsonl').write_text(
        json.dumps({'trace_id': 't1', 'decision': 'OK', 'cycle_time_sec': 0.1}) + '\n',
        encoding='utf-8',
    )
    trace_path = traces / 't1.jsonl'
    trace_path.write_text(json.dumps({'phase': 'capture'}) + '\n', encoding='utf-8')

    store = ResultStore(runtime)
    first = store.get_result('t1')
    assert first is not None
    assert int(first['traceBundle']['eventCount']) == 1

    trace_path.write_text(
        json.dumps({'phase': 'capture'}) + '\n' + json.dumps({'phase': 'analyze'}) + '\n',
        encoding='utf-8',
    )

    second = store.get_result('t1')
    assert second is not None
    assert int(second['traceBundle']['eventCount']) == 2


def test_result_store_tolerates_non_numeric_phase_timings(tmp_path: Path) -> None:
    results_dir = tmp_path / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    with (results_dir / 'result_log.csv').open('w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['time', 'trace_id', 'batch_id', 'item_id', 'recipe_id', 'category', 'defect_type', 'score', 'qr_ok', 'qr_text', 'orientation_ok', 'color_name', 'color_ratio', 'image_path', 'annotated_image_path', 'detail_json'])
        writer.writerow(['2026-03-31T08:00:00Z', 'trace-bad-timing', 'BATCH-1', 1, 'recipe-a', 'COLOR', 'SHIFT', 0.8, True, 'QR-1', True, 'red', 0.9, 'images/raw.png', 'images/ann.png', json.dumps({'processing_ms': 'bad-value'}, ensure_ascii=False)])
    (results_dir / 'cycle_summary.jsonl').write_text(
        json.dumps({'trace_id': 'trace-bad-timing', 'decision': 'NG', 'cycle_time_sec': 'NaN-ish', 'phase_timings_ms': {'feeding': 'oops', 'capture': None, 'analyze': 'also-bad', 'sorting': 'still-bad'}}, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    store = ResultStore(tmp_path)
    detail = store.get_result('trace-bad-timing')
    assert detail is not None
    assert detail['traceId'] == 'trace-bad-timing'
    assert detail['cycleMs'] == 0.0
    assert detail['breakdown']['feedingMs'] == 0.0
    assert detail['breakdown']['captureMs'] == 0.0
    assert detail['breakdown']['analyzeMs'] == 0.0
    assert detail['breakdown']['sortingMs'] == 0.0


def test_result_store_exposes_business_id_accessors(tmp_path: Path) -> None:
    _prepare_logs(tmp_path)
    store = ResultStore(tmp_path)
    assert store.result_ids_for_batch('BATCH-1')[0].startswith('result-BATCH-1-1-2026-03-31T08-00-00Z')
    bundles = store.trace_bundles_for_batch('BATCH-1')
    assert 'trace-1' in bundles



def test_result_store_attaches_read_model_status(tmp_path: Path) -> None:
    _prepare_logs(tmp_path)
    store = ResultStore(tmp_path)
    rows = store.list_results()
    assert rows
    assert rows[0]['readModelStatus']['mode'] in {'HOT', 'PROJECTION_ERROR', 'REPAIR_REQUIRED'}
    assert 'degraded' in rows[0]['readModelStatus']


def test_result_store_fallback_file_scan_tolerates_non_numeric_item_id(tmp_path: Path) -> None:
    results_dir = tmp_path / 'results'
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / 'result_log.csv').write_text(
        'time,trace_id,batch_id,item_id,recipe_id,category,defect_type,score,qr_ok,qr_text,orientation_ok,color_name,color_ratio,image_path,annotated_image_path,detail_json\n'
        '2026-03-31T08:00:00Z,trace-bad-item,BATCH-X,not-a-number,recipe-a,COLOR,SHIFT,0.8,True,QR-1,True,red,0.9,images/raw.png,images/ann.png,{"processing_ms":"bad"}\n',
        encoding='utf-8',
    )
    store = ResultStore(tmp_path, read_model_policy=ReadModelPolicy(fallback_legacy_reads=True))
    store.read_model_repository.refresh_if_needed = lambda: (_ for _ in ()).throw(RuntimeError('force legacy fallback'))  # type: ignore[assignment]
    rows = store.list_results()
    assert rows
    assert rows[0]['itemId'] == -1
    assert rows[0]['cycleMs'] == 0.0



def test_result_store_status_reports_projection_only_mode(tmp_path: Path) -> None:
    _prepare_logs(tmp_path)
    store = ResultStore(tmp_path)
    status = store.read_model_status()
    assert status['fallbackEnabled'] is False
    assert status['querySurface'] == 'projection'
