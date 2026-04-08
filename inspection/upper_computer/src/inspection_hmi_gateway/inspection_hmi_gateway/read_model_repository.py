from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from inspection_utils.logging_tools import safe_json_loads
from inspection_utils.paths import resolve_runtime_path
from inspection_utils.read_model_projection import safe_int as _safe_int
from inspection_utils.read_model_store import ReadModelStore

from .evidence_repository import TraceEvidenceRepository
from .read_model_policy import READ_MODEL_QUERY_REFRESH_DISABLED, ReadModelPolicy, load_read_model_policy
from .read_model_projection_repair import build_result_record, build_summary_map, read_jsonl_dicts, read_result_rows, rebuild_projection, refresh_trace_stream_projection
from .read_model_result_queries import ResultQueryFilters, assemble_result_detail, fetch_result_page, load_result_projection_payload
from .read_model_replay_queries import fetch_trace_page
from .read_model_trace_queries import build_batch_summary, fetch_artifacts_for_trace_ids, fetch_result_ids_for_batch, fetch_result_ids_for_trace_ids, fetch_trace_bundle, fetch_trace_bundles_for_batch, fetch_trace_id_for_result, fetch_trace_ids
from .read_model_sync_coordinator import build_readiness, cached_sync_token, resolve_projection_refresh_plan


class ReadModelRepositoryError(RuntimeError):
    """Base exception for read-model repository failures."""


class ReadModelSyncRequiredError(ReadModelRepositoryError):
    """Raised when the SQLite projection is stale and explicit repair is required."""


class ReadModelRepository:
    """SQLite-backed read model for results, traces, artifacts and events.

    The repository treats SQLite as the primary query surface. File-based rebuild
    remains available through explicit repair APIs, plus an optional bootstrap
    repair when the projection database is empty.
    """

    def __init__(self, log_root: str | Path = 'logs/runtime', *, policy: ReadModelPolicy | None = None) -> None:
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
        self.trace_repository = TraceEvidenceRepository(self.log_root)
        self.policy = policy or load_read_model_policy()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=NORMAL')
        except sqlite3.Error:
            pass
        return conn

    @contextmanager
    def connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self.connection() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS result_entry (
                    result_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    bundle_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS result_source (
                    result_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    row_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trace_bundle (
                    trace_id TEXT PRIMARY KEY,
                    trace_url TEXT NOT NULL DEFAULT '',
                    event_count INTEGER NOT NULL DEFAULT 0,
                    artifact_count INTEGER NOT NULL DEFAULT 0,
                    bundle_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS artifact_entry (
                    trace_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    url TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    artifact_json TEXT NOT NULL,
                    PRIMARY KEY (trace_id, kind, path)
                );
                CREATE TABLE IF NOT EXISTS trace_event (
                    trace_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (trace_id, seq)
                );
                CREATE TABLE IF NOT EXISTS result_lookup (
                    result_id TEXT PRIMARY KEY,
                    trace_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    batch_id TEXT NOT NULL DEFAULT '',
                    item_id INTEGER NOT NULL DEFAULT -1,
                    recipe_id TEXT NOT NULL DEFAULT '',
                    decision TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    defect_type TEXT NOT NULL DEFAULT '',
                    qr_text TEXT NOT NULL DEFAULT '',
                    cycle_ms REAL NOT NULL DEFAULT 0.0,
                    artifact_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS summary_lookup (
                    trace_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL DEFAULT '',
                    item_id INTEGER NOT NULL DEFAULT -1,
                    decision TEXT NOT NULL DEFAULT '',
                    final_status TEXT NOT NULL DEFAULT '',
                    cycle_ms REAL NOT NULL DEFAULT 0.0,
                    processing_ms REAL NOT NULL DEFAULT 0.0,
                    completed_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS artifact_lookup (
                    trace_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    path TEXT NOT NULL,
                    batch_id TEXT NOT NULL DEFAULT '',
                    item_id INTEGER NOT NULL DEFAULT -1,
                    created_at TEXT NOT NULL DEFAULT '',
                    url TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (trace_id, kind, path)
                );
                CREATE TABLE IF NOT EXISTS trace_event_index (
                    trace_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_type TEXT NOT NULL DEFAULT '',
                    event_time TEXT NOT NULL DEFAULT '',
                    batch_id TEXT NOT NULL DEFAULT '',
                    item_id INTEGER NOT NULL DEFAULT -1,
                    PRIMARY KEY (trace_id, seq)
                );
                CREATE INDEX IF NOT EXISTS idx_result_entry_timestamp ON result_entry(timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_artifact_entry_trace ON artifact_entry(trace_id);
                CREATE INDEX IF NOT EXISTS idx_trace_event_trace ON trace_event(trace_id, seq);
                CREATE INDEX IF NOT EXISTS idx_result_lookup_timestamp ON result_lookup(timestamp DESC, result_id DESC);
                CREATE INDEX IF NOT EXISTS idx_result_lookup_batch ON result_lookup(batch_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_result_lookup_recipe ON result_lookup(recipe_id, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_result_lookup_decision ON result_lookup(decision, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_result_lookup_qr ON result_lookup(qr_text, timestamp DESC);
                CREATE INDEX IF NOT EXISTS idx_artifact_lookup_trace ON artifact_lookup(trace_id, kind);
                CREATE INDEX IF NOT EXISTS idx_trace_event_index_type ON trace_event_index(trace_id, event_type, seq);
                """
            )
            self._ensure_schema_columns(conn)

    def _ensure_schema_columns(self, conn: sqlite3.Connection) -> None:
        lookup_columns = {str(row['name']) for row in conn.execute('PRAGMA table_info(result_lookup)').fetchall()}
        if 'qr_text' not in lookup_columns:
            conn.execute("ALTER TABLE result_lookup ADD COLUMN qr_text TEXT NOT NULL DEFAULT ''")
            conn.execute('CREATE INDEX IF NOT EXISTS idx_result_lookup_qr ON result_lookup(qr_text, timestamp DESC)')

    def _file_token(self, path: Path) -> str:
        return self.store.file_token(path)

    def _trace_token(self) -> str:
        return self.store.trace_token()

    def _sync_token(self) -> str:
        return self.store.sync_token()

    def _source_file_tokens(self) -> dict[str, str]:
        """Return lightweight tokens for structured result source files.

        Args:
            None.

        Returns:
            Mapping from logical source file names to file tokens.

        Raises:
            No exception is intentionally raised.

        Boundary behavior:
            Missing files are represented as ``0:0`` tokens.
        """
        return self.store.source_file_tokens()

    def _load_sync_state(self) -> dict[str, Any]:
        return self.store.load_sync_state()

    def _write_sync_state(self, *, sync_token: str, source_files: dict[str, str], trace_token: str) -> None:
        self.store.write_sync_state(sync_token=sync_token, source_files=source_files, trace_token=trace_token)

    def _cached_sync_token(self) -> str:
        """Return the best available source sync token.

        Args:
            None.

        Returns:
            The cached sync token when cached structured-source file tokens still
            match the live files, otherwise a freshly recomputed token.

        Raises:
            No exception is intentionally raised.

        Boundary behavior:
            When any structured source file changed outside the logger-side
            read-model writer, the method falls back to a live token recompute so
            stale projections are detected instead of being masked by the cached
            sync state file.
        """
        return cached_sync_token(self.store)

    def _next_trace_token(self) -> str:
        return self.store.next_trace_token()

    def _update_sync_token_metadata(self, conn: sqlite3.Connection) -> str:
        return self.store.update_sync_token_metadata(conn)

    def _materialized_sync_token(self) -> str:
        return self.store.materialized_sync_token()

    def current_sync_token(self) -> str:
        return self._cached_sync_token()

    def has_projection_data(self) -> bool:
        with self.connection() as conn:
            row = conn.execute('SELECT COUNT(*) AS count FROM result_entry').fetchone()
        return bool(int(row['count']) if row is not None else 0)

    def readiness(self) -> dict[str, Any]:
        projection_available = self.has_projection_data()
        return build_readiness(self.store, self.policy, projection_available=projection_available).as_dict()

    def live_readiness(self) -> dict[str, Any]:
        """Return a strict readiness snapshot using a live sync-token recompute.

        Args:
            None.

        Returns:
            A readiness payload mirroring :meth:`readiness`, but using the live
            source sync token instead of the cached sync-state shortcut.

        Raises:
            No exception is intentionally raised.

        Boundary behavior:
            This method may scan trace file tokens and is therefore reserved for
            detail/replay requests that need stronger freshness guarantees than
            paginated list queries.
        """
        projection_available = self.has_projection_data()
        source_sync_token = self.store.sync_token()
        materialized_sync_token = self.store.materialized_sync_token()
        stale = source_sync_token != materialized_sync_token
        return {
            'mode': self.policy.normalized_mode().upper(),
            'sourceSyncToken': source_sync_token,
            'materializedSyncToken': materialized_sync_token,
            'stale': stale,
            'projectionAvailable': projection_available,
            'repairRequired': stale or not projection_available,
            'querySideTraceRefresh': self.policy.normalized_query_side_trace_refresh().upper(),
        }

    def _ensure_live_projection_fresh(self, *, consumer: str) -> dict[str, Any]:
        """Ensure strict freshness for detail-style projection reads.

        Args:
            consumer: Human-readable consumer identifier for diagnostics.

        Returns:
            The strict readiness payload when the projection is healthy.

        Raises:
            ReadModelSyncRequiredError: When the materialized projection is
                stale or missing and explicit repair is required.

        Boundary behavior:
            The method never triggers repair work. It is deliberately fail-
            closed so detail/replay callers do not hide stale projections.
        """
        readiness = self.live_readiness()
        if not bool(readiness.get('projectionAvailable')):
            raise ReadModelSyncRequiredError(f'SQLite read model has no materialized projection rows; explicit repair is required before serving {consumer}')
        if bool(readiness.get('repairRequired')):
            raise ReadModelSyncRequiredError(f'SQLite read model is stale; explicit repair is required before serving {consumer}')
        return readiness

    def refresh_if_needed(self) -> None:
        projection_available = self.has_projection_data()
        plan = resolve_projection_refresh_plan(self.store, self.policy, projection_available=projection_available)
        if plan.action == 'noop':
            return
        if plan.action == 'rebuild':
            self.rebuild(plan.source_sync_token)
            return
        if plan.reason == 'legacy_mode':
            raise ReadModelSyncRequiredError('read-model policy is set to legacy; SQLite projection refresh is disabled')
        raise ReadModelSyncRequiredError('SQLite read model is stale; explicit repair is required by policy')

    def repair(self) -> None:
        self.rebuild(self._cached_sync_token())

    def rebuild(self, token: str | None = None) -> None:
        """Rebuild the full SQLite projection from structured runtime evidence.

        Args:
            token: Optional source sync token captured by the caller. The value is
                accepted for compatibility with existing callers, but sync-state
                metadata is always written from the live structured sources inside
                the active rebuild transaction.

        Returns:
            None.

        Raises:
            Any underlying repository, file I/O, or SQLite exception.

        Boundary behavior:
            The rebuild fully replaces projection tables, including
            ``result_source``, so subsequent single-trace refreshes cannot reuse
            stale source rows from an older materialization.
        """
        _ = token
        with self.connection() as conn:
            rebuild_projection(conn, store=self.store, trace_repository=self.trace_repository)

    def _result_rows(self) -> list[dict[str, Any]]:
        return read_result_rows(self.result_csv)

    def _read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        return read_jsonl_dicts(path)

    def _summary_map(self) -> dict[str, dict[str, Any]]:
        return build_summary_map(self.summary_jsonl)

    def _build_result_record(self, *, row: dict[str, Any], summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
        return build_result_record(row=row, summaries=summaries, trace_repository=self.trace_repository)

    def _store_result_lookup(self, conn: sqlite3.Connection, record: dict[str, Any]) -> None:
        self.store.upsert_result_lookup(conn, projection=record)

    def query_result_page(self, *, batch_id: str = '', recipe_id: str = '', decision: str = '', defect_type: str = '', qr_text: str = '', from_ts: str = '', to_ts: str = '', limit: int | None = None, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        self.refresh_if_needed()
        filters = ResultQueryFilters(
            batch_id=batch_id,
            recipe_id=recipe_id,
            decision=decision,
            defect_type=defect_type,
            qr_text=qr_text,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        with self.connection() as conn:
            return fetch_result_page(conn, filters, limit=limit, offset=offset)

    def list_results(self) -> list[dict[str, Any]]:
        rows, _ = self.query_result_page()
        return rows

    def _refresh_single_trace_if_needed(self, trace_id: str) -> None:
        """Refresh one trace bundle when its trace-event stream changed.

        Args:
            trace_id: Runtime trace identifier.

        Returns:
            None.

        Raises:
            No exception is intentionally raised. In-place refresh failures are
            intentionally swallowed so callers can continue using the last
            materialized projection.

        Boundary behavior:
            The refresh only reconciles *trace-stream* fields (trace URL, event
            count, and event payloads). Structured evidence such as artifacts,
            summaries, manifests, and top-level projection fields derived from
            them remain sourced from the last materialized SQLite projection
            until a full rebuild/repair occurs. This prevents query-side file
            reads from overwriting hotter logger-side projection state.
        """
        if not trace_id:
            return
        try:
            with self.connection() as conn:
                refresh_trace_stream_projection(conn, store=self.store, trace_repository=self.trace_repository, trace_id=trace_id)
        except Exception:
            return

    def _result_projection_payload(self, result_id: str) -> tuple[dict[str, Any] | None, str]:
        with self.connection() as conn:
            return load_result_projection_payload(conn, str(result_id))

    def _should_refresh_result_trace_bundle(self, trace_id: str) -> bool:
        if not trace_id:
            return False
        refresh_mode = self.policy.normalized_query_side_trace_refresh()
        return refresh_mode != READ_MODEL_QUERY_REFRESH_DISABLED

    def _trace_bundle_from_projection(self, trace_id: str) -> dict[str, Any]:
        if not trace_id:
            return {}
        with self.connection() as conn:
            bundle = fetch_trace_bundle(conn, trace_id)
        if bundle is None:
            return self.trace_repository.trace_bundle(trace_id)
        return bundle

    def _assemble_result_detail(self, *, trace_id: str, projection_payload: dict[str, Any], allow_stale_projection: bool = False) -> dict[str, Any]:
        trace_bundle_loader = self._trace_bundle_from_projection if allow_stale_projection else self.trace_bundle
        return assemble_result_detail(projection_payload, trace_id=trace_id, trace_bundle_loader=trace_bundle_loader)

    def _get_result_from_projection(self, result_id: str, *, allow_stale_projection: bool = False) -> dict[str, Any] | None:
        """Load one materialized result detail without inline repair/refresh.

        Args:
            result_id: Business result identifier or trace identifier.
            allow_stale_projection: Whether the trace bundle loader may serve the
                current materialized projection even when the projection is known
                stale. Callers should use this only for explicit compatibility
                branches; the default query surface remains projection-only and
                fail-closed.

        Returns:
            The normalized materialized result payload, or ``None`` when no
            matching projection row exists.

        Raises:
            No exception is intentionally raised here. Projection freshness is
            enforced by the caller before entering this method.

        Boundary behavior:
            The method never performs inline trace refreshes or file-system
            repair work. It only assembles a response from already materialized
            SQLite projection rows.
        """
        payload, trace_id = self._result_projection_payload(result_id)
        if payload is None:
            return None
        return self._assemble_result_detail(trace_id=trace_id, projection_payload=payload, allow_stale_projection=allow_stale_projection)

    def get_result(self, result_id: str) -> dict[str, Any] | None:
        """Return one result projection by result identifier or trace identifier.

        Args:
            result_id: Business result identifier or trace identifier.

        Returns:
            The normalized result projection, or ``None`` when no result exists.

        Raises:
            Any repository refresh exception from :meth:`refresh_if_needed`.

        Boundary behavior:
            ``traceBundle`` is always returned in the result-detail payload.
            The method is projection-only and never performs inline file-system
            refresh/repair work on behalf of the caller.
        """
        self.refresh_if_needed()
        self._ensure_live_projection_fresh(consumer='result details')
        return self._get_result_from_projection(result_id)

    def get_result_from_projection(self, result_id: str) -> dict[str, Any] | None:
        """Return a result detail using the current SQLite projection only.

        Args:
            result_id: Business result identifier or trace identifier.

        Returns:
            The normalized result projection, or ``None`` when the current
            materialized projection contains no matching row.

        Raises:
            ReadModelSyncRequiredError: When no materialized projection is
                available and serving a stale detail would therefore become an
                implicit file-scan fallback.

        Boundary behavior:
            This method intentionally skips :meth:`refresh_if_needed` so callers
            can serve an already-materialized detail while separately surfacing
            that the projection is stale and requires explicit repair.
        """
        self._ensure_live_projection_fresh(consumer='result details')
        return self._get_result_from_projection(result_id, allow_stale_projection=False)

    def query_trace_page(
        self,
        *,
        batch_id: str = '',
        decision: str = '',
        q: str = '',
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        self.refresh_if_needed()
        with self.connection() as conn:
            return fetch_trace_page(conn, batch_id=batch_id, decision=decision, q=q, limit=limit, offset=offset)

    def list_trace_ids(self) -> list[str]:
        self.refresh_if_needed()
        with self.connection() as conn:
            return fetch_trace_ids(conn)

    def trace_bundle(self, trace_id: str) -> dict[str, Any]:
        """Return one materialized trace bundle from the SQLite projection.

        Args:
            trace_id: Target trace identifier.

        Returns:
            The materialized trace bundle when present, otherwise the persisted
            trace bundle from the evidence repository for backfilled historical
            traces that were not projected.

        Raises:
            Any exception raised by :meth:`refresh_if_needed` when the read
            model is stale and explicit repair is required.

        Boundary behavior:
            The method never performs inline single-trace refreshes. Callers
            must repair the read model explicitly before requesting fresh trace
            details.
        """
        self.refresh_if_needed()
        self._ensure_live_projection_fresh(consumer='trace bundles')
        with self.connection() as conn:
            row = conn.execute('SELECT bundle_json FROM trace_bundle WHERE trace_id=?', (str(trace_id),)).fetchone()
        if row is None:
            return self.trace_repository.trace_bundle(trace_id)
        return safe_json_loads(str(row['bundle_json']) or '{}')

    def trace_id_for_result(self, result_id: str) -> str:
        self.refresh_if_needed()
        with self.connection() as conn:
            return fetch_trace_id_for_result(conn, result_id)

    def result_ids_for_batch(self, batch_id: str) -> list[str]:
        self.refresh_if_needed()
        with self.connection() as conn:
            return fetch_result_ids_for_batch(conn, batch_id)

    def result_ids_for_trace_ids(self, trace_ids: list[str]) -> list[str]:
        self.refresh_if_needed()
        with self.connection() as conn:
            return fetch_result_ids_for_trace_ids(conn, trace_ids)

    def trace_bundles_for_batch(self, batch_id: str) -> dict[str, dict[str, Any]]:
        self.refresh_if_needed()
        with self.connection() as conn:
            return fetch_trace_bundles_for_batch(conn, batch_id)

    def artifacts_for_trace_ids(self, trace_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        self.refresh_if_needed()
        with self.connection() as conn:
            return fetch_artifacts_for_trace_ids(conn, trace_ids)

    def artifact_records_for_result_ids(self, result_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        mapping: dict[str, list[dict[str, Any]]] = {}
        trace_ids = [self.trace_id_for_result(result_id) for result_id in result_ids]
        grouped = self.artifacts_for_trace_ids([trace_id for trace_id in trace_ids if trace_id])
        for result_id, trace_id in zip(result_ids, trace_ids):
            mapping[str(result_id)] = grouped.get(trace_id, []) if trace_id else []
        return mapping

    def batch_summary(self, *, batch_id: str) -> dict[str, Any]:
        self.refresh_if_needed()
        with self.connection() as conn:
            return build_batch_summary(conn, batch_id=batch_id)
