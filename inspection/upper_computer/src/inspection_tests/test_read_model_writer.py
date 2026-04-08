from __future__ import annotations

import csv
from pathlib import Path

from inspection_hmi_gateway.read_model_repository import ReadModelRepository
from inspection_logger.read_model_writer import ReadModelWriter


def _seed_runtime_dirs(root: Path) -> None:
    (root / 'results').mkdir(parents=True, exist_ok=True)
    (root / 'traces').mkdir(parents=True, exist_ok=True)
    (root / 'config_snapshot').mkdir(parents=True, exist_ok=True)
    with (root / 'results' / 'result_log.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['time', 'trace_id', 'batch_id', 'item_id', 'recipe_id', 'category', 'defect_type', 'score', 'qr_ok', 'qr_text', 'orientation_ok', 'color_name', 'color_ratio', 'image_path', 'annotated_image_path', 'detail_json'])
    for name in ('cycle_summary.jsonl', 'replay_manifest.jsonl', 'artifact_index.jsonl'):
        (root / 'results' / name).write_text('', encoding='utf-8')


def test_read_model_writer_keeps_sqlite_projection_hot(tmp_path: Path) -> None:
    log_root = tmp_path / 'logs'
    _seed_runtime_dirs(log_root)
    trace_path = log_root / 'traces' / 'trace-writer.jsonl'
    trace_path.write_text('{"type":"cycle_finish","trace_id":"trace-writer"}\n', encoding='utf-8')
    writer = ReadModelWriter(log_root)
    writer.record_trace_event('trace-writer', {'type': 'cycle_finish', 'trace_id': 'trace-writer', 'decision': 'OK'})
    writer.record_artifact(trace_id='trace-writer', kind='raw', path='captures/raw.png', batch_id='B-1', item_id=1, source='artifact_index', meta={})
    writer.record_summary({'trace_id': 'trace-writer', 'batch_id': 'B-1', 'item_id': 1, 'decision': 'OK', 'cycle_time_sec': 1.2}, run_artifacts={'profile_name': 'production'}, config_snapshot={'recipe_path': 'config_snapshot/recipe.yaml'})
    writer.record_result_row({
        'time': '2026-01-01T00:00:00Z',
        'trace_id': 'trace-writer',
        'batch_id': 'B-1',
        'item_id': 1,
        'recipe_id': 'recipe-a',
        'category': 'surface',
        'defect_type': 'NONE',
        'score': '0.98',
        'qr_ok': 'True',
        'qr_text': 'QR-1',
        'orientation_ok': 'True',
        'color_name': 'red',
        'color_ratio': '0.9',
        'image_path': 'captures/raw.png',
        'annotated_image_path': '',
        'detail_json': '{"trace_id":"trace-writer"}',
    })

    repo = ReadModelRepository(log_root)
    detail = repo.get_result('trace-writer')
    assert detail is not None
    assert detail['traceId'] == 'trace-writer'
    assert detail['artifactCount'] == 1
    assert detail['traceBundle']['summary']['decision'] == 'OK'



def test_read_model_writer_populates_fine_grained_indexes(tmp_path: Path) -> None:
    log_root = tmp_path / 'logs'
    _seed_runtime_dirs(log_root)
    writer = ReadModelWriter(log_root)
    writer.record_trace_event('trace-indexed', {'type': 'capture_request', 'time': '2026-01-01T00:00:01Z', 'trace_id': 'trace-indexed', 'batch_id': 'B-2', 'item_id': 2})
    writer.record_summary({'trace_id': 'trace-indexed', 'batch_id': 'B-2', 'item_id': 2, 'decision': 'NG', 'final_status': 'FAULT', 'cycle_time_sec': 0.8, 'processing_ms': 123.4}, run_artifacts={}, config_snapshot={})
    writer.record_result_row({
        'time': '2026-01-01T00:00:02Z',
        'trace_id': 'trace-indexed',
        'batch_id': 'B-2',
        'item_id': 2,
        'recipe_id': 'recipe-b',
        'category': 'surface',
        'defect_type': 'SCRATCH',
        'score': '0.12',
        'qr_ok': 'False',
        'qr_text': 'QR-2',
        'orientation_ok': 'True',
        'color_name': 'blue',
        'color_ratio': '0.1',
        'image_path': '',
        'annotated_image_path': '',
        'detail_json': '{"trace_id":"trace-indexed"}',
    })
    with writer.connection() as conn:
        result_row = conn.execute('SELECT batch_id, decision, cycle_ms FROM result_lookup WHERE trace_id=?', ('trace-indexed',)).fetchone()
        summary_row = conn.execute('SELECT final_status, processing_ms FROM summary_lookup WHERE trace_id=?', ('trace-indexed',)).fetchone()
        event_row = conn.execute('SELECT event_type, batch_id FROM trace_event_index WHERE trace_id=?', ('trace-indexed',)).fetchone()
    assert result_row is not None
    assert str(result_row['batch_id']) == 'B-2'
    assert str(result_row['decision']) == 'NG'
    assert float(result_row['cycle_ms']) >= 800.0
    assert summary_row is not None
    assert str(summary_row['final_status']) == 'FAULT'
    assert float(summary_row['processing_ms']) == 123.4
    assert event_row is not None
    assert str(event_row['event_type']) == 'capture_request'
    assert str(event_row['batch_id']) == 'B-2'


def test_read_model_writer_keeps_projection_hot_when_trace_events_are_recorded(tmp_path: Path) -> None:
    log_root = tmp_path / 'logs'
    _seed_runtime_dirs(log_root)
    trace_path = log_root / 'traces' / 'trace-hot.jsonl'
    trace_path.write_text('{"type":"cycle_finish","trace_id":"trace-hot"}\n', encoding='utf-8')

    writer = ReadModelWriter(log_root)
    writer.record_trace_event('trace-hot', {'type': 'cycle_finish', 'trace_id': 'trace-hot'})
    writer.record_artifact(trace_id='trace-hot', kind='raw', path='captures/raw.png', batch_id='B-HOT', item_id=7, source='artifact_index', meta={})
    writer.record_summary({'trace_id': 'trace-hot', 'batch_id': 'B-HOT', 'item_id': 7, 'decision': 'OK', 'cycle_time_sec': 0.5}, run_artifacts={}, config_snapshot={})
    writer.record_result_row({
        'time': '2026-01-01T00:00:00Z',
        'trace_id': 'trace-hot',
        'batch_id': 'B-HOT',
        'item_id': 7,
        'recipe_id': 'recipe-hot',
        'category': 'surface',
        'defect_type': 'NONE',
        'score': '0.99',
        'qr_ok': 'True',
        'qr_text': 'QR-HOT',
        'orientation_ok': 'True',
        'color_name': 'red',
        'color_ratio': '0.9',
        'image_path': 'captures/raw.png',
        'annotated_image_path': '',
        'detail_json': '{"trace_id":"trace-hot"}',
    })

    writer.record_trace_event('trace-hot', {'type': 'inspection_result', 'trace_id': 'trace-hot'})

    repo = ReadModelRepository(log_root)
    detail = repo.get_result('trace-hot')
    assert detail is not None
    assert detail['artifactCount'] == 1
    assert int(detail['traceBundle']['eventCount']) == 2
    assert int(detail['traceBundle']['artifactCount']) == 1
