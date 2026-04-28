from __future__ import annotations

import sqlite3
from typing import Any

from inspection_utils.logging_common import safe_json_loads


def fetch_trace_page(
    conn: sqlite3.Connection,
    *,
    batch_id: str = '',
    decision: str = '',
    q: str = '',
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    where = []
    params: list[Any] = []
    if batch_id:
        where.append('summary_lookup.batch_id = ?')
        params.append(batch_id)
    if decision:
        where.append('summary_lookup.decision = ?')
        params.append(decision)
    if q:
        like = f'%{q}%'
        where.append('(trace_bundle.trace_id LIKE ? OR summary_lookup.batch_id LIKE ? OR summary_lookup.decision LIKE ?)')
        params.extend([like, like, like])
    where_clause = f"WHERE {' AND '.join(where)}" if where else ''
    total = int(conn.execute(
        f'''SELECT COUNT(*) AS count
            FROM trace_bundle
            LEFT JOIN summary_lookup ON summary_lookup.trace_id = trace_bundle.trace_id
            {where_clause}''',
        params,
    ).fetchone()['count'])
    rows = conn.execute(
        f'''SELECT
                trace_bundle.trace_id,
                trace_bundle.trace_url,
                trace_bundle.artifact_count,
                trace_bundle.bundle_json,
                summary_lookup.batch_id,
                summary_lookup.decision,
                summary_lookup.completed_at
            FROM trace_bundle
            LEFT JOIN summary_lookup ON summary_lookup.trace_id = trace_bundle.trace_id
            {where_clause}
            ORDER BY COALESCE(summary_lookup.completed_at, '') DESC, trace_bundle.trace_id DESC
            LIMIT ? OFFSET ?''',
        [*params, int(limit), int(offset)],
    ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        bundle = safe_json_loads(row['bundle_json'], default={})
        items.append({
            'traceId': row['trace_id'],
            'batchId': row['batch_id'] or '',
            'decision': row['decision'] or '',
            'completedAt': row['completed_at'] or '',
            'summary': bundle.get('summary', {}),
            'runArtifacts': bundle.get('runArtifacts', {}),
            'configSnapshot': bundle.get('configSnapshot', {}),
            'artifactCount': int(row['artifact_count'] or 0),
            'artifacts': bundle.get('artifacts', []),
            'traceUrl': row['trace_url'] or '',
        })
    return items, total
