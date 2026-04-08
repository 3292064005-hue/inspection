from __future__ import annotations

"""SQLite storage core for gateway metadata persistence."""

import hashlib
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def token_digest(token: str) -> str:
    return hashlib.sha256(str(token).encode('utf-8')).hexdigest()


class MetadataSqliteStore:
    """Own SQLite connection lifecycle and schema migration for gateway metadata."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
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
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    role TEXT NOT NULL,
                    action TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    result TEXT NOT NULL,
                    correlation_id TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS operator_session (
                    token_digest TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    client_ip TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 1
                );

                CREATE TABLE IF NOT EXISTS export_job (
                    job_id TEXT PRIMARY KEY,
                    batch_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL DEFAULT '',
                    requested_by TEXT NOT NULL,
                    export_url TEXT NOT NULL DEFAULT '',
                    item_count INTEGER NOT NULL DEFAULT 0,
                    trace_count INTEGER NOT NULL DEFAULT 0,
                    detail_json TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS action_job (
                    job_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    message TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT '',
                    completed_at TEXT NOT NULL DEFAULT '',
                    requested_by TEXT NOT NULL,
                    requested_role TEXT NOT NULL DEFAULT '',
                    cancellable INTEGER NOT NULL DEFAULT 1,
                    action_topic TEXT NOT NULL DEFAULT '',
                    action_type TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    result_json TEXT NOT NULL DEFAULT '{}',
                    error_json TEXT NOT NULL DEFAULT '{}',
                    feedback_json TEXT NOT NULL DEFAULT '{}'
                );
                """
            )
            self._ensure_schema_columns(conn)

    def _ensure_schema_columns(self, conn: sqlite3.Connection) -> None:
        columns = {str(row['name']) for row in conn.execute("PRAGMA table_info(operator_session)").fetchall()}
        if 'token' in columns and 'token_digest' not in columns:
            conn.execute('ALTER TABLE operator_session RENAME TO operator_session_legacy')
            conn.executescript(
                """
                CREATE TABLE operator_session (
                    token_digest TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    client_ip TEXT NOT NULL DEFAULT '',
                    user_agent TEXT NOT NULL DEFAULT '',
                    is_active INTEGER NOT NULL DEFAULT 1
                );
                """
            )
            for row in conn.execute('SELECT * FROM operator_session_legacy').fetchall():
                conn.execute(
                    """
                    INSERT OR REPLACE INTO operator_session(token_digest, username, display_name, role, issued_at, expires_at, last_seen_at, client_ip, user_agent, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        token_digest(str(row['token'])),
                        str(row['username']),
                        str(row['display_name']),
                        str(row['role']),
                        str(row['issued_at']),
                        str(row['expires_at']),
                        str(row['last_seen_at']),
                        str(row['client_ip']),
                        str(row['user_agent']),
                        int(row['is_active']),
                    ),
                )
            conn.execute('DROP TABLE operator_session_legacy')

        action_columns = {str(row['name']) for row in conn.execute("PRAGMA table_info(action_job)").fetchall()}
        if 'action_topic' not in action_columns:
            conn.execute("ALTER TABLE action_job ADD COLUMN action_topic TEXT NOT NULL DEFAULT ''")
        if 'action_type' not in action_columns:
            conn.execute("ALTER TABLE action_job ADD COLUMN action_type TEXT NOT NULL DEFAULT ''")
        if 'feedback_json' not in action_columns:
            conn.execute("ALTER TABLE action_job ADD COLUMN feedback_json TEXT NOT NULL DEFAULT '{}'")
