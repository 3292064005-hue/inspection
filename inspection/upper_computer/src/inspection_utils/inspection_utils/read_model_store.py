from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .logging_tools import safe_json_loads
from .paths import relative_artifact_path, resolve_runtime_path
from .read_model_projection import safe_float, safe_int


class ReadModelStore:
    def __init__(self, log_root: str | Path = 'logs/runtime', *, start: str | None = None) -> None:
        self.log_root = resolve_runtime_path(log_root, start=start or __file__)
        self.results_root = self.log_root / 'results'
        self.traces_root = self.log_root / 'traces'
        self.result_csv = self.results_root / 'result_log.csv'
        self.summary_jsonl = self.results_root / 'cycle_summary.jsonl'
        self.replay_manifest_jsonl = self.results_root / 'replay_manifest.jsonl'
        self.artifact_index_jsonl = self.results_root / 'artifact_index.jsonl'
        self.db_path = self.results_root / 'read_model.sqlite3'
        self.sync_state_path = self.results_root / 'read_model_sync_state.json'
        self.results_root.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def connect(self) -> sqlite3.Connection:
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
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connection() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS result_entry (result_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, timestamp TEXT NOT NULL, bundle_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS result_source (result_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, row_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS trace_bundle (trace_id TEXT PRIMARY KEY, trace_url TEXT NOT NULL DEFAULT '', event_count INTEGER NOT NULL DEFAULT 0, artifact_count INTEGER NOT NULL DEFAULT 0, bundle_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS artifact_entry (trace_id TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, url TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '', artifact_json TEXT NOT NULL, PRIMARY KEY (trace_id, kind, path));
            CREATE TABLE IF NOT EXISTS trace_event (trace_id TEXT NOT NULL, seq INTEGER NOT NULL, event_json TEXT NOT NULL, PRIMARY KEY (trace_id, seq));
            CREATE TABLE IF NOT EXISTS result_lookup (result_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, timestamp TEXT NOT NULL, batch_id TEXT NOT NULL DEFAULT '', item_id INTEGER NOT NULL DEFAULT -1, recipe_id TEXT NOT NULL DEFAULT '', decision TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT '', defect_type TEXT NOT NULL DEFAULT '', qr_text TEXT NOT NULL DEFAULT '', cycle_ms REAL NOT NULL DEFAULT 0.0, artifact_count INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS summary_lookup (trace_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL DEFAULT '', item_id INTEGER NOT NULL DEFAULT -1, decision TEXT NOT NULL DEFAULT '', final_status TEXT NOT NULL DEFAULT '', cycle_ms REAL NOT NULL DEFAULT 0.0, processing_ms REAL NOT NULL DEFAULT 0.0, completed_at TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS artifact_lookup (trace_id TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, batch_id TEXT NOT NULL DEFAULT '', item_id INTEGER NOT NULL DEFAULT -1, created_at TEXT NOT NULL DEFAULT '', url TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '', PRIMARY KEY (trace_id, kind, path));
            CREATE TABLE IF NOT EXISTS trace_event_index (trace_id TEXT NOT NULL, seq INTEGER NOT NULL, event_type TEXT NOT NULL DEFAULT '', event_time TEXT NOT NULL DEFAULT '', batch_id TEXT NOT NULL DEFAULT '', item_id INTEGER NOT NULL DEFAULT -1, PRIMARY KEY (trace_id, seq));
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
            """)
            self.ensure_schema_columns(conn)

    def ensure_schema_columns(self, conn: sqlite3.Connection) -> None:
        lookup_columns = {str(row['name']) for row in conn.execute('PRAGMA table_info(result_lookup)').fetchall()}
        if 'qr_text' not in lookup_columns:
            conn.execute("ALTER TABLE result_lookup ADD COLUMN qr_text TEXT NOT NULL DEFAULT ''")
        conn.execute('CREATE INDEX IF NOT EXISTS idx_result_lookup_recipe ON result_lookup(recipe_id, timestamp DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_result_lookup_decision ON result_lookup(decision, timestamp DESC)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_result_lookup_qr ON result_lookup(qr_text, timestamp DESC)')

    def file_token(self, path: Path) -> str:
        if not path.exists():
            return '0:0'
        stat = path.stat()
        return f"{int(stat.st_mtime_ns)}:{int(stat.st_size)}"

    def trace_token(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(self.traces_root.glob('*.jsonl')):
            digest.update(path.name.encode('utf-8'))
            digest.update(self.file_token(path).encode('utf-8'))
        return digest.hexdigest()

    def sync_token(self) -> str:
        return '|'.join([self.file_token(self.result_csv), self.file_token(self.summary_jsonl), self.file_token(self.replay_manifest_jsonl), self.file_token(self.artifact_index_jsonl), self.trace_token()])

    def source_file_tokens(self) -> dict[str, str]:
        return {'result_csv': self.file_token(self.result_csv), 'summary_jsonl': self.file_token(self.summary_jsonl), 'replay_manifest_jsonl': self.file_token(self.replay_manifest_jsonl), 'artifact_index_jsonl': self.file_token(self.artifact_index_jsonl)}

    def load_sync_state(self) -> dict[str, Any]:
        if not self.sync_state_path.exists():
            return {}
        try:
            payload = json.loads(self.sync_state_path.read_text(encoding='utf-8'))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def write_sync_state(self, *, sync_token: str, source_files: dict[str, str], trace_token: str) -> None:
        self.sync_state_path.write_text(json.dumps({'version': 1, 'syncToken': sync_token, 'traceToken': trace_token, 'sourceFiles': dict(source_files)}, ensure_ascii=False, indent=2), encoding='utf-8')

    def next_trace_token(self) -> str:
        state = self.load_sync_state(); current = str(state.get('traceToken', 'trace-rev-0'))
        if current.startswith('trace-rev-'):
            try: revision = int(current.rsplit('-', 1)[-1]) + 1
            except ValueError: revision = 1
        else: revision = 1
        return f'trace-rev-{revision}'

    def update_sync_token_metadata(self, conn: sqlite3.Connection) -> str:
        """Persist the current materialized sync token metadata.

        Args:
            conn: Open SQLite connection participating in the current write
                transaction.

        Returns:
            The exact sync token representing the structured source files and
            current trace-file token at the time the projection was written.

        Raises:
            sqlite3.Error: Any database write failure from the caller's
                transaction context.

        Boundary behavior:
            The stored ``traceToken`` reflects the live trace-file token instead
            of a synthetic revision counter so detail/replay reads can detect
            external trace mutations without relying on query-side repair.
        """
        source_files = self.source_file_tokens()
        trace_token = self.trace_token()
        sync_token = '|'.join([source_files['result_csv'], source_files['summary_jsonl'], source_files['replay_manifest_jsonl'], source_files['artifact_index_jsonl'], trace_token])
        conn.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES ('sync_token', ?)", (sync_token,))
        self.write_sync_state(sync_token=sync_token, source_files=source_files, trace_token=trace_token)
        return sync_token

    def materialized_sync_token(self) -> str:
        with self.connection() as conn: row = conn.execute("SELECT value FROM metadata WHERE key='sync_token'").fetchone()
        return str(row['value']) if row is not None else ''

    def trace_path(self, trace_id: str) -> Path: return self.traces_root / f'{trace_id}.jsonl'
    def trace_url(self, trace_id: str) -> str:
        trace_path = self.trace_path(trace_id)
        return f"/artifacts/{relative_artifact_path(self.log_root, trace_path)}" if trace_path.exists() else ''

    def existing_bundle(self, conn: sqlite3.Connection, trace_id: str) -> dict[str, Any]:
        row = conn.execute('SELECT bundle_json FROM trace_bundle WHERE trace_id=?', (trace_id,)).fetchone(); return {} if row is None else safe_json_loads(str(row['bundle_json']) or '{}')
    def events(self, conn: sqlite3.Connection, trace_id: str) -> list[dict[str, Any]]:
        return [safe_json_loads(str(r['event_json']) or '{}') for r in conn.execute('SELECT event_json FROM trace_event WHERE trace_id=? ORDER BY seq ASC', (trace_id,)).fetchall()]
    def artifacts(self, conn: sqlite3.Connection, trace_id: str) -> list[dict[str, Any]]:
        return [safe_json_loads(str(r['artifact_json']) or '{}') for r in conn.execute('SELECT artifact_json FROM artifact_entry WHERE trace_id=? ORDER BY kind ASC, path ASC', (trace_id,)).fetchall()]
    def store_bundle(self, conn: sqlite3.Connection, trace_id: str, bundle: dict[str, Any]) -> None:
        conn.execute('INSERT OR REPLACE INTO trace_bundle(trace_id, trace_url, event_count, artifact_count, bundle_json) VALUES (?, ?, ?, ?, ?)', (trace_id, str(bundle.get('traceUrl', '')), safe_int(bundle.get('eventCount', 0), 0), safe_int(bundle.get('artifactCount', 0), 0), json.dumps(bundle, ensure_ascii=False)))
    def store_result_entry(self, conn: sqlite3.Connection, projection: dict[str, Any]) -> None:
        conn.execute('INSERT OR REPLACE INTO result_entry(result_id, trace_id, timestamp, bundle_json) VALUES (?, ?, ?, ?)', (str(projection.get('id', '')), str(projection.get('traceId', '')), str(projection.get('timestamp', '')), json.dumps(projection, ensure_ascii=False)))
    def store_result_source(self, conn: sqlite3.Connection, *, result_id: str, trace_id: str, row: dict[str, Any]) -> None:
        conn.execute('INSERT OR REPLACE INTO result_source(result_id, trace_id, row_json) VALUES (?, ?, ?)', (str(result_id), str(trace_id), json.dumps(row, ensure_ascii=False)))
    def latest_result_source(self, conn: sqlite3.Connection, trace_id: str) -> dict[str, Any]:
        row = conn.execute('SELECT row_json FROM result_source WHERE trace_id=? ORDER BY result_id DESC LIMIT 1', (trace_id,)).fetchone(); return {} if row is None else safe_json_loads(str(row['row_json']) or '{}')
    def upsert_result_lookup(self, conn: sqlite3.Connection, *, projection: dict[str, Any], row: dict[str, Any] | None = None) -> None:
        source_row = row or projection
        conn.execute('INSERT OR REPLACE INTO result_lookup(result_id, trace_id, timestamp, batch_id, item_id, recipe_id, decision, category, defect_type, qr_text, cycle_ms, artifact_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (str(projection.get('id', '')), str(projection.get('traceId', '')), str(projection.get('timestamp', '')), str(projection.get('batchId', source_row.get('batch_id', ''))), safe_int(source_row.get('item_id', projection.get('itemId', -1)), -1), str(projection.get('recipeId', source_row.get('recipe_id', ''))), str(projection.get('decision', '')), str(projection.get('category', source_row.get('category', ''))), str(projection.get('defectType', source_row.get('defect_type', ''))), str(projection.get('qrText', source_row.get('qr_text', ''))), safe_float(projection.get('cycleMs', 0.0), 0.0), safe_int(projection.get('artifactCount', 0), 0)))
    def upsert_summary_lookup(self, conn: sqlite3.Connection, *, trace_id: str, summary: dict[str, Any]) -> None:
        conn.execute('INSERT OR REPLACE INTO summary_lookup(trace_id, batch_id, item_id, decision, final_status, cycle_ms, processing_ms, completed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (trace_id, str(summary.get('batch_id', '')), safe_int(summary.get('item_id', -1), -1), str(summary.get('decision', '')), str(summary.get('final_status', '')), safe_float(summary.get('cycle_time_sec', 0.0), 0.0) * 1000.0, safe_float(summary.get('processing_ms', 0.0), 0.0), str(summary.get('completed_at', ''))))
    def upsert_artifact(self, conn: sqlite3.Connection, *, trace_id: str, artifact: dict[str, Any]) -> None:
        kind = str(artifact.get('kind', 'artifact')); path = str(artifact.get('path', ''))
        conn.execute('INSERT OR REPLACE INTO artifact_entry(trace_id, kind, path, url, source, artifact_json) VALUES (?, ?, ?, ?, ?, ?)', (trace_id, kind, path, str(artifact.get('url', '')), str(artifact.get('source', '')), json.dumps(artifact, ensure_ascii=False)))
        conn.execute('INSERT OR REPLACE INTO artifact_lookup(trace_id, kind, path, batch_id, item_id, created_at, url, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (trace_id, kind, path, str(artifact.get('batchId', '')), safe_int(artifact.get('itemId', -1), -1), str(artifact.get('createdAt', '')), str(artifact.get('url', '')), str(artifact.get('source', ''))))
    def replace_trace_events(self, conn: sqlite3.Connection, *, trace_id: str, events: list[dict[str, Any]]) -> None:
        conn.execute('DELETE FROM trace_event WHERE trace_id=?', (trace_id,)); conn.execute('DELETE FROM trace_event_index WHERE trace_id=?', (trace_id,))
        for idx, event in enumerate(events):
            if not isinstance(event, dict): continue
            conn.execute('INSERT OR REPLACE INTO trace_event(trace_id, seq, event_json) VALUES (?, ?, ?)', (trace_id, idx, json.dumps(event, ensure_ascii=False)))
            conn.execute('INSERT OR REPLACE INTO trace_event_index(trace_id, seq, event_type, event_time, batch_id, item_id) VALUES (?, ?, ?, ?, ?, ?)', (trace_id, idx, str(event.get('type', '')), str(event.get('time', '')), str(event.get('batch_id', '')), safe_int(event.get('item_id', -1), -1)))
    def append_trace_event(self, conn: sqlite3.Connection, *, trace_id: str, event: dict[str, Any]) -> None:
        row = conn.execute('SELECT COALESCE(MAX(seq), -1) AS seq FROM trace_event WHERE trace_id=?', (trace_id,)).fetchone(); seq = safe_int(row['seq'] if row is not None else -1, -1) + 1
        conn.execute('INSERT OR REPLACE INTO trace_event(trace_id, seq, event_json) VALUES (?, ?, ?)', (trace_id, seq, json.dumps(event, ensure_ascii=False)))
        conn.execute('INSERT OR REPLACE INTO trace_event_index(trace_id, seq, event_type, event_time, batch_id, item_id) VALUES (?, ?, ?, ?, ?, ?)', (trace_id, seq, str(event.get('type', '')), str(event.get('time', '')), str(event.get('batch_id', '')), safe_int(event.get('item_id', -1), -1)))
