from __future__ import annotations

"""Read-model writer utilities for logger-side projection materialization."""

from pathlib import Path
from typing import Any

from inspection_utils.io_common import resolve_runtime_path
from inspection_utils.model_common import build_result_projection
from inspection_utils.model_common import ReadModelStore
from inspection_utils.model_common import canonical_result_id


def _normalize_artifact_path(path: str | Path) -> str:
    """Normalize artifact paths into a stable, URL-safe relative representation.

    Args:
        path: Artifact filesystem path or path-like string.

    Returns:
        Forward-slash normalized relative path without a leading slash.

    Raises:
        TypeError: If ``path`` is ``None``.

    Boundary behavior:
        Empty strings are returned as empty strings so callers can decide whether
        to skip persistence or raise a contract error.
    """
    if path is None:
        raise TypeError('path must not be None')
    return str(path).replace('\\', '/').lstrip('/')


class ReadModelWriter:
    """Materialize logger-side read-model projections from runtime evidence."""

    def __init__(self, log_root: str | Path = 'logs/runtime') -> None:
        self.log_root = resolve_runtime_path(log_root, start=__file__)
        self.store = ReadModelStore(self.log_root, start=__file__)
        self.results_root = self.store.results_root
        self.traces_root = self.store.traces_root
        self.result_csv = self.store.result_csv
        self.summary_jsonl = self.store.summary_jsonl
        self.replay_manifest_jsonl = self.store.replay_manifest_jsonl
        self.artifact_index_jsonl = self.store.artifact_index_jsonl
        self.db_path = self.store.db_path
        self.sync_state_path = self.store.sync_state_path

    def connection(self):
        """Return the underlying read-model store connection context manager."""
        return self.store.connection()

    def _refresh_bundle(
        self,
        conn,
        trace_id: str,
        *,
        summary: dict[str, Any] | None = None,
        run_artifacts: dict[str, Any] | None = None,
        config_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Rebuild and persist the full trace bundle for one trace identifier."""
        existing = self.store.existing_bundle(conn, trace_id)
        events = self.store.events(conn, trace_id)
        artifacts = self.store.artifacts(conn, trace_id)
        if summary is None:
            summary = existing.get('summary', {}) if isinstance(existing.get('summary', {}), dict) else {}
        if run_artifacts is None:
            run_artifacts = existing.get('runArtifacts', {}) if isinstance(existing.get('runArtifacts', {}), dict) else {}
        if config_snapshot is None:
            config_snapshot = existing.get('configSnapshot', {}) if isinstance(existing.get('configSnapshot', {}), dict) else {}
        bundle = {
            'traceId': trace_id,
            'traceUrl': self.store.trace_url(trace_id),
            'eventCount': len(events),
            'events': events,
            'summary': dict(summary or {}),
            'runArtifacts': dict(run_artifacts or {}),
            'configSnapshot': dict(config_snapshot or {}),
            'artifacts': artifacts,
            'artifactCount': len(artifacts),
        }
        self.store.store_bundle(conn, trace_id, bundle)
        return bundle

    def record_trace_event(self, trace_id: str, event: dict[str, Any]) -> None:
        """Persist one trace event and refresh dependent read-model projections."""
        if not trace_id:
            return
        with self.connection() as conn:
            self.store.append_trace_event(conn, trace_id=trace_id, event=event)
            self._refresh_bundle(conn, trace_id)
            self._refresh_result_projection(conn, trace_id)
            self.store.update_sync_token_metadata(conn)

    def record_artifact(
        self,
        *,
        trace_id: str,
        kind: str,
        path: str,
        batch_id: str,
        item_id: int,
        source: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        """Persist one artifact entry and keep trace/result projections aligned.

        Args:
            trace_id: Trace identifier owning the artifact.
            kind: Artifact category label.
            path: Artifact relative or absolute path.
            batch_id: Batch identifier associated with the trace.
            item_id: Batch item index.
            source: Producer node or subsystem name.
            meta: Optional metadata attached to the artifact.

        Returns:
            None.

        Raises:
            TypeError: When ``path`` is ``None``.

        Boundary behavior:
            Empty ``trace_id`` or normalized empty paths are ignored so upstream
            callers can safely emit partial runtime events without corrupting the
            read model.
        """
        if not trace_id or not path:
            return
        normalized_path = _normalize_artifact_path(path)
        if not normalized_path:
            return
        artifact = {
            'traceId': trace_id,
            'kind': kind,
            'path': normalized_path,
            'url': f'/artifacts/{normalized_path}',
            'source': source,
            'batchId': batch_id,
            'itemId': item_id,
            'createdAt': str(meta.get('created_at', '') if isinstance(meta, dict) else ''),
            'meta': dict(meta or {}),
        }
        with self.connection() as conn:
            self.store.upsert_artifact(conn, trace_id=trace_id, artifact=artifact)
            self._refresh_bundle(conn, trace_id)
            self._refresh_result_projection(conn, trace_id)
            self.store.update_sync_token_metadata(conn)

    def record_summary(self, summary: dict[str, Any], *, run_artifacts: dict[str, Any], config_snapshot: dict[str, Any]) -> None:
        """Persist one inspection summary and refresh dependent projections."""
        trace_id = str(summary.get('trace_id', ''))
        if not trace_id:
            return
        with self.connection() as conn:
            self.store.upsert_summary_lookup(conn, trace_id=trace_id, summary=summary)
            self._refresh_bundle(conn, trace_id, summary=summary, run_artifacts=run_artifacts, config_snapshot=config_snapshot)
            self._refresh_result_projection(conn, trace_id)
            self.store.update_sync_token_metadata(conn)

    def record_result_row(self, row: dict[str, Any]) -> None:
        """Persist one raw result row and rematerialize the latest projection."""
        trace_id = str(row.get('trace_id', ''))
        if not trace_id:
            return
        result_id = canonical_result_id(
            result_id=row.get('result_id', ''),
            trace_id=trace_id,
            batch_id=row.get('batch_id', ''),
            item_id=row.get('item_id', ''),
            timestamp=row.get('time', ''),
        )
        with self.connection() as conn:
            self.store.store_result_source(conn, result_id=result_id, trace_id=trace_id, row=row)
            self._refresh_result_projection(conn, trace_id)
            self.store.update_sync_token_metadata(conn)

    def _refresh_result_projection(self, conn, trace_id: str) -> None:
        """Recompute the latest result projection for the provided trace."""
        row = self.store.latest_result_source(conn, trace_id)
        if not row:
            return
        bundle = self.store.existing_bundle(conn, trace_id)
        summary = bundle.get('summary', {}) if isinstance(bundle.get('summary', {}), dict) else {}
        projection = build_result_projection(row=row, summary=summary, trace_bundle=bundle)
        self.store.store_result_entry(conn, projection)
        self.store.upsert_result_lookup(conn, projection=projection, row=row)
