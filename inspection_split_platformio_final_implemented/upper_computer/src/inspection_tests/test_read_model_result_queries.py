from __future__ import annotations

import json
import sqlite3

from inspection_hmi_gateway.read_model_result_queries import ResultQueryFilters, assemble_result_detail, fetch_result_page, load_result_projection_payload


def test_result_query_helpers_filter_page_and_assemble_detail() -> None:
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("CREATE TABLE result_lookup(result_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, timestamp TEXT NOT NULL, batch_id TEXT NOT NULL DEFAULT '', item_id INTEGER NOT NULL DEFAULT -1, recipe_id TEXT NOT NULL DEFAULT '', decision TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '', defect_type TEXT NOT NULL DEFAULT '', qr_text TEXT NOT NULL DEFAULT '', cycle_ms REAL NOT NULL DEFAULT 0.0, artifact_count INTEGER NOT NULL DEFAULT 0)")
        conn.execute("CREATE TABLE result_entry(result_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, timestamp TEXT NOT NULL, bundle_json TEXT NOT NULL)")
        conn.execute("INSERT INTO result_lookup(result_id, trace_id, timestamp, batch_id, item_id, recipe_id, decision, category, defect_type, qr_text, cycle_ms, artifact_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", ('RID-1', 'TRACE-1', '2026-04-03T00:00:00Z', 'B-1', 1, 'recipe-a', 'OK', 'OK', 'NONE', 'QR-1', 12.0, 2))
        conn.execute(
            "INSERT INTO result_entry(result_id, trace_id, timestamp, bundle_json) VALUES (?, ?, ?, ?)",
            ('RID-1', 'TRACE-1', '2026-04-03T00:00:00Z', json.dumps({'id': 'RID-1', 'traceId': 'TRACE-1', 'decision': 'OK'})),
        )

        rows, total = fetch_result_page(conn, ResultQueryFilters(batch_id='B-1'), limit=10, offset=0)
        assert total == 1
        assert rows[0]['id'] == 'RID-1'

        payload, trace_id = load_result_projection_payload(conn, 'RID-1')
        assert payload is not None
        assert trace_id == 'TRACE-1'

        detail = assemble_result_detail(payload, trace_id=trace_id, trace_bundle_loader=lambda current_trace_id: {'traceId': current_trace_id, 'eventCount': 3})
        assert detail['traceBundle']['traceId'] == 'TRACE-1'
        assert detail['traceBundle']['eventCount'] == 3
    finally:
        conn.close()
