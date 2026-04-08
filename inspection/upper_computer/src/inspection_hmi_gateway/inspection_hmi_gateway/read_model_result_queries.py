from __future__ import annotations

"""Helpers for read-model result queries and result-detail assembly.

This module keeps the SQL filtering/lookup logic separate from
``ReadModelRepository`` so the repository can focus on synchronization,
projection refresh, and storage orchestration.
"""

from dataclasses import dataclass
import sqlite3
from typing import Any, Callable

from inspection_utils.logging_tools import safe_json_loads


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
