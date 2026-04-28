from __future__ import annotations

"""Helpers for read-model result queries and result-detail assembly.

This module keeps the SQL filtering/lookup logic separate from
``ReadModelRepository`` so the repository can focus on synchronization,
projection refresh, and storage orchestration.
"""

from dataclasses import dataclass
import sqlite3
from typing import Any, Callable

from inspection_utils.logging_common import safe_json_loads


@dataclass(frozen=True, slots=True)
class ResultQueryFilters:
    """Normalized filters for querying result projections."""

    batch_id: str = ''
    recipe_id: str = ''
    decision: str = ''
    defect_type: str = ''
    qr_text: str = ''
    from_ts: str = ''
    to_ts: str = ''


def build_result_lookup_where_clause(filters: ResultQueryFilters) -> tuple[str, list[Any]]:
    """Build the shared ``result_lookup`` SQL WHERE clause."""
    clauses: list[str] = []
    args: list[Any] = []
    if filters.batch_id:
        clauses.append('rl.batch_id = ?')
        args.append(filters.batch_id)
    if filters.recipe_id:
        clauses.append('rl.recipe_id = ?')
        args.append(filters.recipe_id)
    if filters.decision:
        clauses.append('rl.decision = ?')
        args.append(filters.decision)
    if filters.defect_type:
        clauses.append('rl.defect_type LIKE ?')
        args.append(f'%{filters.defect_type}%')
    if filters.qr_text:
        clauses.append('rl.qr_text LIKE ?')
        args.append(f'%{filters.qr_text}%')
    if filters.from_ts:
        clauses.append('rl.timestamp >= ?')
        args.append(filters.from_ts)
    if filters.to_ts:
        clauses.append('rl.timestamp <= ?')
        args.append(filters.to_ts)
    return (' WHERE ' + ' AND '.join(clauses)) if clauses else '', args


def fetch_result_page(conn: sqlite3.Connection, filters: ResultQueryFilters, *, limit: int | None = None, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
    """Fetch one paginated page of result projections from SQLite."""
    where_clause, args = build_result_lookup_where_clause(filters)
    total_row = conn.execute(f'SELECT COUNT(*) AS count FROM result_lookup rl{where_clause}', args).fetchone()
    total = int(total_row['count']) if total_row is not None else 0
    sql = f'SELECT re.bundle_json FROM result_lookup rl JOIN result_entry re ON re.result_id = rl.result_id{where_clause} ORDER BY rl.timestamp DESC, rl.result_id DESC'
    query_args = list(args)
    if limit is not None and limit >= 0:
        sql += ' LIMIT ? OFFSET ?'
        query_args.extend([int(limit), max(0, int(offset))])
    elif offset > 0:
        sql += ' LIMIT -1 OFFSET ?'
        query_args.append(max(0, int(offset)))
    rows = conn.execute(sql, query_args).fetchall()
    return [safe_json_loads(str(row['bundle_json']) or '{}') for row in rows], total


def load_result_projection_payload(conn: sqlite3.Connection, result_id: str) -> tuple[dict[str, Any] | None, str]:
    """Load one result projection by result ID or trace ID."""
    row = conn.execute(
        'SELECT bundle_json, trace_id FROM result_entry WHERE result_id=? OR trace_id=? LIMIT 1',
        (str(result_id), str(result_id)),
    ).fetchone()
    if row is None:
        return None, ''
    payload = safe_json_loads(str(row['bundle_json']) or '{}')
    return payload, str(row['trace_id'])


def assemble_result_detail(projection_payload: dict[str, Any], *, trace_id: str, trace_bundle_loader: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    """Attach a stable ``traceBundle`` to the result-detail payload."""
    payload = dict(projection_payload)
    payload['traceBundle'] = trace_bundle_loader(trace_id) if trace_id else {}
    return payload


def percentile_value(values: list[float], percentile: float) -> float:
    """Return a stable percentile from an ascending or unsorted numeric sample."""
    if not values:
        return 0.0
    ordered = sorted(float(value) for value in values)
    rank = max(0, min(len(ordered) - 1, int(((max(0.0, min(100.0, float(percentile))) / 100.0) * len(ordered)) + 0.999999) - 1))
    return float(ordered[rank])


def fetch_result_statistics(conn: sqlite3.Connection, filters: ResultQueryFilters, *, sample_limit: int = 120) -> dict[str, Any]:
    """Build a query-driven statistics snapshot from the materialized result projection."""
    where_clause, args = build_result_lookup_where_clause(filters)
    summary_row = conn.execute(
        f"SELECT COUNT(*) AS total, SUM(CASE WHEN rl.decision='OK' THEN 1 ELSE 0 END) AS ok_count, SUM(CASE WHEN rl.decision='NG' THEN 1 ELSE 0 END) AS ng_count, SUM(CASE WHEN rl.decision='RECHECK' THEN 1 ELSE 0 END) AS recheck_count, AVG(rl.cycle_ms) AS avg_cycle_ms FROM result_lookup rl{where_clause}",
        args,
    ).fetchone()
    cycle_rows = conn.execute(f"SELECT rl.cycle_ms FROM result_lookup rl{where_clause} AND rl.cycle_ms > 0" if where_clause else "SELECT rl.cycle_ms FROM result_lookup rl WHERE rl.cycle_ms > 0", args).fetchall()
    decision_rows = conn.execute(f"SELECT rl.decision, COUNT(*) AS count FROM result_lookup rl{where_clause} GROUP BY rl.decision ORDER BY count DESC, rl.decision ASC", args).fetchall()
    defect_rows = conn.execute(f"SELECT CASE WHEN rl.decision='OK' THEN '无缺陷' WHEN rl.defect_type='' THEN '未知' ELSE rl.defect_type END AS label, COUNT(*) AS count FROM result_lookup rl{where_clause} GROUP BY label ORDER BY count DESC, label ASC", args).fetchall()
    recipe_rows = conn.execute(
        f"SELECT rl.recipe_id, COUNT(*) AS total, SUM(CASE WHEN rl.decision='OK' THEN 1 ELSE 0 END) AS ok_count, SUM(CASE WHEN rl.decision='NG' THEN 1 ELSE 0 END) AS ng_count, SUM(CASE WHEN rl.decision='RECHECK' THEN 1 ELSE 0 END) AS recheck_count FROM result_lookup rl{where_clause} GROUP BY rl.recipe_id ORDER BY total DESC, rl.recipe_id ASC",
        args,
    ).fetchall()
    samples, _total = fetch_result_page(conn, filters, limit=max(1, int(sample_limit)), offset=0)
    sample_rows = list(reversed(samples))
    cycle_values = [float(row['cycle_ms'] if isinstance(row, sqlite3.Row) else row[0]) for row in cycle_rows]
    total = int(summary_row['total'] or 0) if summary_row is not None else 0
    ok_count = int(summary_row['ok_count'] or 0) if summary_row is not None else 0
    ng_count = int(summary_row['ng_count'] or 0) if summary_row is not None else 0
    recheck_count = int(summary_row['recheck_count'] or 0) if summary_row is not None else 0
    avg_cycle_ms = round(float(summary_row['avg_cycle_ms'] or 0.0), 3) if summary_row is not None else 0.0
    return {
        'filters': {
            'batchId': filters.batch_id,
            'recipeId': filters.recipe_id,
            'decision': filters.decision,
            'defectType': filters.defect_type,
            'qrText': filters.qr_text,
            'from': filters.from_ts,
            'to': filters.to_ts,
        },
        'summary': {
            'total': total,
            'okCount': ok_count,
            'ngCount': ng_count,
            'recheckCount': recheck_count,
            'yieldRate': round((ok_count / total), 4) if total else 0.0,
            'avgCycleMs': avg_cycle_ms,
            'p95CycleMs': round(percentile_value(cycle_values, 95.0), 3),
            'sampleCount': len(sample_rows),
        },
        'decisionBreakdown': [{'decision': str(row['decision'] or 'UNKNOWN'), 'count': int(row['count'] or 0)} for row in decision_rows],
        'defectBreakdown': [{'name': str(row['label'] or '未知'), 'count': int(row['count'] or 0)} for row in defect_rows],
        'recipeBreakdown': [
            {
                'recipeId': str(row['recipe_id'] or ''),
                'total': int(row['total'] or 0),
                'okCount': int(row['ok_count'] or 0),
                'ngCount': int(row['ng_count'] or 0),
                'recheckCount': int(row['recheck_count'] or 0),
                'yieldRate': round((float(row['ok_count'] or 0) / float(row['total'] or 1)), 4) if int(row['total'] or 0) else 0.0,
            }
            for row in recipe_rows
        ],
        'cycleTrend': [
            {
                'id': str(item.get('id', '')),
                'timestamp': str(item.get('timestamp', '')),
                'cycleMs': float(item.get('cycleMs', 0.0) or 0.0),
                'decision': str(item.get('decision', '')),
                'recipeId': str(item.get('recipeId', '')),
                'recipeName': str(item.get('recipeName', item.get('recipeId', ''))),
            }
            for item in sample_rows if isinstance(item, dict)
        ],
    }
