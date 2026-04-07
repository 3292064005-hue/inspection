from __future__ import annotations

"""Focused trace/result lookup queries for the read-model repository."""

import sqlite3
from typing import Any

from inspection_utils.logging_tools import safe_json_loads


def fetch_trace_ids(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        'SELECT trace_id FROM trace_bundle UNION SELECT trace_id FROM summary_lookup UNION SELECT trace_id FROM artifact_lookup UNION SELECT trace_id FROM trace_event_index UNION SELECT trace_id FROM result_lookup ORDER BY trace_id'
    ).fetchall()
    return [str(row['trace_id']) for row in rows if str(row['trace_id'])]


def fetch_trace_bundle(conn: sqlite3.Connection, trace_id: str) -> dict[str, Any] | None:
    row = conn.execute('SELECT bundle_json FROM trace_bundle WHERE trace_id=?', (str(trace_id),)).fetchone()
    if row is None:
        return None
    return safe_json_loads(str(row['bundle_json']) or '{}')


def fetch_trace_id_for_result(conn: sqlite3.Connection, result_id: str) -> str:
    row = conn.execute('SELECT trace_id FROM result_lookup WHERE result_id=? LIMIT 1', (str(result_id),)).fetchone()
    return '' if row is None else str(row['trace_id'])


def fetch_result_ids_for_batch(conn: sqlite3.Connection, batch_id: str) -> list[str]:
    rows = conn.execute('SELECT result_id FROM result_lookup WHERE batch_id=? ORDER BY timestamp DESC, result_id DESC', (str(batch_id),)).fetchall()
    return [str(row['result_id']) for row in rows if str(row['result_id'])]


def fetch_trace_bundles_for_batch(conn: sqlite3.Connection, batch_id: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        'SELECT DISTINCT tb.trace_id, tb.bundle_json FROM trace_bundle tb JOIN result_lookup rl ON rl.trace_id = tb.trace_id WHERE rl.batch_id=? ORDER BY tb.trace_id',
        (str(batch_id),),
    ).fetchall()
    return {str(row['trace_id']): safe_json_loads(str(row['bundle_json']) or '{}') for row in rows if str(row['trace_id'])}


def fetch_artifacts_for_trace_ids(conn: sqlite3.Connection, trace_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    normalized = [str(item) for item in trace_ids if str(item)]
    if not normalized:
        return {}
    placeholders = ','.join('?' for _ in normalized)
    rows = conn.execute(
        f'SELECT trace_id, artifact_json FROM artifact_entry WHERE trace_id IN ({placeholders}) ORDER BY trace_id, kind, path',
        tuple(normalized),
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = {trace_id: [] for trace_id in normalized}
    for row in rows:
        trace_id = str(row['trace_id'])
        grouped.setdefault(trace_id, []).append(safe_json_loads(str(row['artifact_json']) or '{}'))
    return grouped


def build_batch_summary(conn: sqlite3.Connection, *, batch_id: str) -> dict[str, Any]:
    row = conn.execute(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN decision='OK' THEN 1 ELSE 0 END) AS ok_count, SUM(CASE WHEN decision='NG' THEN 1 ELSE 0 END) AS ng_count, SUM(CASE WHEN decision='RECHECK' THEN 1 ELSE 0 END) AS recheck_count, AVG(cycle_ms) AS avg_cycle_ms FROM result_lookup WHERE batch_id=?",
        (batch_id,),
    ).fetchone()
    return {
        'batchId': batch_id,
        'total': int(row['total'] or 0) if row is not None else 0,
        'okCount': int(row['ok_count'] or 0) if row is not None else 0,
        'ngCount': int(row['ng_count'] or 0) if row is not None else 0,
        'recheckCount': int(row['recheck_count'] or 0) if row is not None else 0,
        'avgCycleMs': round(float(row['avg_cycle_ms'] or 0.0), 3) if row is not None else 0.0,
    }
