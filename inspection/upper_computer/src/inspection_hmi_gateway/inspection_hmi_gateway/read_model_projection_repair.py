from __future__ import annotations

"""Projection rebuild and trace-refresh helpers for the read model.

The repository owns policy/application flow, while this module owns the
mechanics of rebuilding SQLite projection tables from structured runtime files
and reconciling a single trace-stream refresh.
"""

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from inspection_utils.model_common import build_result_projection
from inspection_utils.model_common import ReadModelStore

from .evidence_repository import TraceEvidenceRepository


def read_result_rows(result_csv: Path) -> list[dict[str, Any]]:
    """Read structured CSV result rows for projection rebuilds."""
    if not result_csv.exists():
        return []
    with result_csv.open('r', encoding='utf-8', newline='') as handle:
        return list(csv.DictReader(handle))


def read_jsonl_dicts(path: Path) -> list[dict[str, Any]]:
    """Read one JSONL file, discarding blank or malformed rows."""
    if not path.exists():
        return []
    payload: list[dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                payload.append(item)
    return payload


def build_summary_map(summary_jsonl: Path) -> dict[str, dict[str, Any]]:
    """Index cycle-summary rows by trace identifier."""
    return {str(item.get('trace_id', '')): item for item in read_jsonl_dicts(summary_jsonl)}


def build_result_record(*, row: dict[str, Any], summaries: dict[str, dict[str, Any]], trace_repository: TraceEvidenceRepository) -> dict[str, Any]:
    """Build one result projection record from structured source evidence."""
    trace_id = str(row.get('trace_id', ''))
    summary = summaries.get(trace_id, {})
    trace_bundle = trace_repository.trace_bundle(trace_id) if trace_id else {}
    return build_result_projection(row=row, summary=summary, trace_bundle=trace_bundle)


def rebuild_projection(conn: sqlite3.Connection, *, store: ReadModelStore, trace_repository: TraceEvidenceRepository) -> None:
    """Rebuild the entire SQLite projection from structured runtime files.

    Args:
        conn: Open SQLite connection inside the repository transaction scope.
        store: Runtime read-model store for file and table helpers.
        trace_repository: File-backed trace evidence repository.

    Returns:
        None.

    Raises:
        Any underlying I/O, JSON, or SQLite error is propagated to the caller.

    Boundary behavior:
        Existing projection tables are fully replaced, including
        ``result_source``. This ensures future single-trace refreshes do not
        read stale source rows left behind from older materializations.
    """
    rows = read_result_rows(store.result_csv)
    summaries = build_summary_map(store.summary_jsonl)
    trace_ids = set(trace_repository.list_trace_ids())
    trace_ids.update(str(row.get('trace_id', '')) for row in rows if str(row.get('trace_id', '')))
    records = [build_result_record(row=row, summaries=summaries, trace_repository=trace_repository) for row in rows]

    conn.execute('DELETE FROM result_entry')
    conn.execute('DELETE FROM result_source')
    conn.execute('DELETE FROM trace_bundle')
    conn.execute('DELETE FROM artifact_entry')
    conn.execute('DELETE FROM trace_event')
    conn.execute('DELETE FROM result_lookup')
    conn.execute('DELETE FROM summary_lookup')
    conn.execute('DELETE FROM artifact_lookup')
    conn.execute('DELETE FROM trace_event_index')

    for row, record in zip(rows, records):
        store.store_result_entry(conn, record)
        store.store_result_source(conn, result_id=str(record.get('id', '')), trace_id=str(record.get('traceId', '')), row=row)
        store.upsert_result_lookup(conn, projection=record, row=row)

    for trace_id in sorted(item for item in trace_ids if item):
        bundle = trace_repository.trace_bundle(trace_id)
        store.store_bundle(conn, trace_id, bundle)
        summary = bundle.get('summary', {}) if isinstance(bundle.get('summary', {}), dict) else {}
        store.upsert_summary_lookup(conn, trace_id=trace_id, summary=summary)
        for artifact in bundle.get('artifacts', []):
            if isinstance(artifact, dict):
                store.upsert_artifact(conn, trace_id=trace_id, artifact=artifact)
        live_events = [event for event in bundle.get('events', []) if isinstance(event, dict)]
        store.replace_trace_events(conn, trace_id=trace_id, events=live_events)

    store.update_sync_token_metadata(conn)


def refresh_trace_stream_projection(conn: sqlite3.Connection, *, store: ReadModelStore, trace_repository: TraceEvidenceRepository, trace_id: str) -> bool:
    """Refresh one materialized trace bundle from the latest trace evidence.

    Args:
        conn: Open SQLite connection inside the repository transaction scope.
        store: Runtime read-model store for table helpers.
        trace_repository: File-backed trace evidence repository.
        trace_id: Runtime trace identifier.

    Returns:
        ``True`` when the materialized bundle changed, otherwise ``False``.

    Raises:
        Any repository or SQLite error is propagated to the caller.

    Boundary behavior:
        The refresh reconciles the current trace file together with structured
        evidence that is scoped to the same trace identifier, including summary,
        artifact, and manifest-derived fields. This keeps result-detail reads
        fresh without requiring a workspace-wide rebuild.
    """
    if not trace_id:
        return False

    live_bundle = trace_repository.trace_bundle(trace_id)
    existing = store.existing_bundle(conn, trace_id)
    if existing == live_bundle:
        return False

    live_events = [event for event in live_bundle.get('events', []) if isinstance(event, dict)]
    live_summary = live_bundle.get('summary', {}) if isinstance(live_bundle.get('summary', {}), dict) else {}
    live_artifacts = [artifact for artifact in live_bundle.get('artifacts', []) if isinstance(artifact, dict)]
    existing_summary = existing.get('summary', {}) if isinstance(existing.get('summary', {}), dict) else {}
    existing_run_artifacts = existing.get('runArtifacts', {}) if isinstance(existing.get('runArtifacts', {}), dict) else {}
    existing_config_snapshot = existing.get('configSnapshot', {}) if isinstance(existing.get('configSnapshot', {}), dict) else {}
    existing_artifacts = [artifact for artifact in existing.get('artifacts', []) if isinstance(artifact, dict)] if isinstance(existing, dict) else []

    merged_bundle = dict(existing) if isinstance(existing, dict) else {}
    merged_bundle.update({
        'traceId': trace_id,
        'traceUrl': str(live_bundle.get('traceUrl', '')),
        'eventCount': len(live_events),
        'events': live_events,
        'summary': live_summary or existing_summary,
        'runArtifacts': live_bundle.get('runArtifacts', {}) if isinstance(live_bundle.get('runArtifacts', {}), dict) and live_bundle.get('runArtifacts', {}) else existing_run_artifacts,
        'configSnapshot': live_bundle.get('configSnapshot', {}) if isinstance(live_bundle.get('configSnapshot', {}), dict) and live_bundle.get('configSnapshot', {}) else existing_config_snapshot,
        'artifacts': live_artifacts or existing_artifacts,
    })
    merged_bundle['artifactCount'] = len(merged_bundle.get('artifacts', []))

    store.store_bundle(conn, trace_id, merged_bundle)
    store.upsert_summary_lookup(conn, trace_id=trace_id, summary=merged_bundle.get('summary', {}))
    conn.execute('DELETE FROM artifact_entry WHERE trace_id=?', (str(trace_id),))
    conn.execute('DELETE FROM artifact_lookup WHERE trace_id=?', (str(trace_id),))
    for artifact in merged_bundle.get('artifacts', []):
        if isinstance(artifact, dict):
            store.upsert_artifact(conn, trace_id=trace_id, artifact=artifact)
    store.replace_trace_events(conn, trace_id=trace_id, events=live_events)

    row_payload = store.latest_result_source(conn, trace_id)
    if row_payload:
        projection = build_result_projection(row=row_payload, summary=merged_bundle.get('summary', {}), trace_bundle=merged_bundle)
        store.store_result_entry(conn, projection)
        store.upsert_result_lookup(conn, projection=projection, row=row_payload)
    return True
