from __future__ import annotations

import csv
import json
from pathlib import Path
from zipfile import ZipFile

from inspection_hmi_gateway.export_service import BatchExportService
from inspection_hmi_gateway.recipe_store import RecipeStore
from inspection_hmi_gateway.result_store import ResultStore


def _write_logs(root: Path) -> None:
    (root / 'results').mkdir(parents=True, exist_ok=True)
    (root / 'events').mkdir(parents=True, exist_ok=True)
    (root / 'traces').mkdir(parents=True, exist_ok=True)
    (root / 'images').mkdir(parents=True, exist_ok=True)
    (root / 'images' / 'raw.png').write_bytes(b'raw')
    (root / 'images' / 'ann.png').write_bytes(b'ann')

    with (root / 'results' / 'result_log.csv').open('w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['time', 'trace_id', 'batch_id', 'item_id', 'recipe_id', 'category', 'defect_type', 'score', 'qr_ok', 'qr_text', 'orientation_ok', 'color_name', 'color_ratio', 'image_path', 'annotated_image_path', 'detail_json'])
        writer.writerow(['2026-03-31T08:00:00Z', 'trace-export', 'BATCH-EXPORT', 1, 'recipe-export', 'COLOR', 'SHIFT', 0.81, True, 'QR100', True, 'red', 0.8, 'images/raw.png', 'images/ann.png', json.dumps({'warnings': ['偏色'], 'processing_ms': 18.2}, ensure_ascii=False)])
    with (root / 'results' / 'cycle_summary.jsonl').open('w', encoding='utf-8') as fh:
        fh.write(json.dumps({'trace_id': 'trace-export', 'decision': 'NG', 'cycle_time_sec': 0.3}, ensure_ascii=False) + '\n')
    with (root / 'events' / 'event_log.jsonl').open('w', encoding='utf-8') as fh:
        fh.write(json.dumps({'type': 'cycle_started', 'batch_id': 'BATCH-EXPORT', 'trace_id': 'trace-export'}, ensure_ascii=False) + '\n')
    (root / 'traces' / 'trace-export.jsonl').write_text(json.dumps({'type': 'inspection_result', 'trace_id': 'trace-export'}, ensure_ascii=False) + '\n', encoding='utf-8')


def test_export_batch_creates_real_zip(tmp_path: Path) -> None:
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    store = RecipeStore(recipes_root)
    store.save_from_hmi({
        'id': 'recipe-export',
        'name': '导出配方',
        'version': '1.0.0',
        'updatedBy': 'tester',
        'roi': [1, 2, 3, 4],
        'qrRoi': [5, 6, 7, 8],
    })
    store.activate('recipe-export')

    service = BatchExportService(log_root=logs_root, result_store=ResultStore(logs_root), recipe_store=store)
    artifacts = service.export_batch('BATCH-EXPORT')

    assert artifacts.export_path.exists()
    with ZipFile(artifacts.export_path) as zf:
        names = set(zf.namelist())
        assert 'manifest.json' in names
        assert 'batch_summary.json' in names
        assert 'results.csv' in names
        assert 'results.json' in names
        assert 'events.jsonl' in names
        assert 'traces/trace-export.jsonl' in names
        assert any(name.startswith('artifacts/raw/') for name in names)
        manifest = json.loads(zf.read('manifest.json').decode('utf-8'))
        assert manifest['batchId'] == 'BATCH-EXPORT'
        assert manifest['itemCount'] == 1
        assert manifest['resultIds'][0].startswith('result-BATCH-EXPORT-1-2026-03-31T08-00-00Z')
        assert manifest['traceIds'] == ['trace-export']


def test_export_batch_ignores_artifacts_outside_log_root(tmp_path: Path) -> None:
    logs_root = tmp_path / 'logs'
    recipes_root = tmp_path / 'recipes'
    _write_logs(logs_root)
    store = RecipeStore(recipes_root)
    store.save_from_hmi({
        'id': 'recipe-export',
        'name': '导出配方',
        'version': '1.0.0',
        'updatedBy': 'tester',
        'roi': [1, 2, 3, 4],
        'qrRoi': [5, 6, 7, 8],
    })
    store.activate('recipe-export')
    outside = tmp_path / 'outside.png'
    outside.write_bytes(b'outside')
    with (logs_root / 'results' / 'result_log.csv').open('a', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['2026-03-31T08:00:01Z', 'trace-export-2', 'BATCH-EXPORT', 2, 'recipe-export', 'OK', '', 0.99, True, 'QR101', True, 'red', 0.8, str(outside), '', json.dumps({}, ensure_ascii=False)])
    service = BatchExportService(log_root=logs_root, result_store=ResultStore(logs_root), recipe_store=store)

    artifacts = service.export_batch('BATCH-EXPORT')

    with ZipFile(artifacts.export_path) as zf:
        names = set(zf.namelist())
        assert not any('outside.png' in name for name in names)
