from __future__ import annotations

import csv
import json
from pathlib import Path

from inspection_hmi_gateway.result_store import ResultStore


def _prepare_logs(root: Path) -> None:
    results_dir = root / 'results'
    traces_dir = root / 'traces'
    results_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)
    with (results_dir / 'result_log.csv').open('w', encoding='utf-8', newline='') as fh:
        writer = csv.writer(fh)
        writer.writerow(['time', 'trace_id', 'batch_id', 'item_id', 'recipe_id', 'category', 'defect_type', 'score', 'qr_ok', 'qr_text', 'orientation_ok', 'color_name', 'color_ratio', 'image_path', 'annotated_image_path', 'detail_json'])
        writer.writerow(['2026-03-31T08:00:00Z', 'trace-1', 'BATCH-1', 1, 'recipe-a', 'COLOR', 'RED_SHIFT', 0.91, True, 'QR001', True, 'red', 0.8, 'images/raw-1.png', 'images/ann-1.png', json.dumps({'warnings': ['色偏'], 'processing_ms': 12.5}, ensure_ascii=False)])
    with (results_dir / 'cycle_summary.jsonl').open('w', encoding='utf-8') as fh:
        fh.write(json.dumps({'trace_id': 'trace-1', 'decision': 'NG', 'cycle_time_sec': 0.123}, ensure_ascii=False) + '\n')


def test_result_store_query_page_does_not_preload_list_results_on_refresh(tmp_path: Path) -> None:
    _prepare_logs(tmp_path)
    store = ResultStore(tmp_path)
    store.read_model_repository.list_results = lambda: (_ for _ in ()).throw(AssertionError('query path must not preload the full result table'))  # type: ignore[assignment]

    rows, total = store.query_result_page(batch_id='BATCH-1')

    assert total == 1
    assert rows[0]['traceId'] == 'trace-1'
