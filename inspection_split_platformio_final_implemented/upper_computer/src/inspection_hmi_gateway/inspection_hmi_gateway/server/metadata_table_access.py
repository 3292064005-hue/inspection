from __future__ import annotations

"""Table-focused accessors for gateway metadata persistence."""

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from inspection_utils.logging_tools import safe_json_loads

from .metadata_database import safe_int, token_digest


@dataclass(slots=True)
class AuditLogStore:
    storage: Any

    def append(self, payload: dict[str, Any]) -> None:
        with self.storage.connection() as conn:
            conn.execute(
                'INSERT INTO audit_log(ts, actor, role, action, resource, result, correlation_id, details_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (
                    str(payload.get('ts', '')),
                    str(payload.get('actor', 'anonymous')),
                    str(payload.get('role', 'viewer')),
                    str(payload.get('action', 'UNKNOWN')),
                    str(payload.get('resource', '')),
                    str(payload.get('result', 'SUCCESS')),
                    str(payload.get('correlationId', '')),
                    json.dumps(payload.get('details', {}), ensure_ascii=False),
                ),
            )

    def list(self, *, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        with self.storage.connection() as conn:
            total = int(conn.execute('SELECT COUNT(*) FROM audit_log').fetchone()[0])
            rows = conn.execute('SELECT * FROM audit_log ORDER BY id DESC LIMIT ? OFFSET ?', (int(limit), int(offset))).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    'id': int(row['id']),
                    'timestamp': str(row['ts']),
                    'actor': str(row['actor']),
                    'role': str(row['role']),
                    'action': str(row['action']),
                    'resource': str(row['resource']),
                    'result': str(row['result']),
                    'correlationId': str(row['correlation_id']),
                    'details': json.loads(str(row['details_json']) or '{}'),
                }
            )
        return items, total


@dataclass(slots=True)
class SessionStore:
    storage: Any

    def upsert(self, payload: dict[str, Any]) -> None:
        with self.storage.connection() as conn:
            conn.execute(
                """
                INSERT INTO operator_session(token_digest, username, display_name, role, issued_at, expires_at, last_seen_at, client_ip, user_agent, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(token_digest) DO UPDATE SET
                  last_seen_at=excluded.last_seen_at,
                  expires_at=excluded.expires_at,
                  client_ip=excluded.client_ip,
                  user_agent=excluded.user_agent,
                  is_active=1
                """,
                (
                    token_digest(str(payload.get('token', ''))),
                    str(payload.get('username', '')),
                    str(payload.get('displayName', payload.get('username', ''))),
                    str(payload.get('role', 'viewer')),
                    str(payload.get('issuedAt', '')),
                    str(payload.get('expiresAt', '')),
                    str(payload.get('lastSeenAt', payload.get('issuedAt', ''))),
                    str(payload.get('clientIp', '')),
                    str(payload.get('userAgent', '')),
                ),
            )

    def deactivate(self, token: str) -> None:
        with self.storage.connection() as conn:
            conn.execute('UPDATE operator_session SET is_active=0 WHERE token_digest=?', (token_digest(str(token)),))

    def get_active(self, token: str) -> dict[str, Any] | None:
        with self.storage.connection() as conn:
            row = conn.execute(
                'SELECT * FROM operator_session WHERE token_digest=? AND is_active=1',
                (token_digest(str(token)),),
            ).fetchone()
        if row is None:
            return None
        return {
            'token': str(token),
            'username': str(row['username']),
            'displayName': str(row['display_name']),
            'role': str(row['role']),
            'issuedAt': str(row['issued_at']),
            'expiresAt': str(row['expires_at']),
            'lastSeenAt': str(row['last_seen_at']),
            'clientIp': str(row['client_ip']),
            'userAgent': str(row['user_agent']),
            'bootstrap': False,
            'mustChangePassword': False,
        }


@dataclass(slots=True)
class ExportJobStore:
    storage: Any

    def record(self, payload: dict[str, Any]) -> None:
        with self.storage.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO export_job(job_id, batch_id, status, created_at, completed_at, requested_by, export_url, item_count, trace_count, detail_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(payload.get('jobId', '')),
                    str(payload.get('batchId', '')),
                    str(payload.get('status', 'COMPLETED')),
                    str(payload.get('createdAt', '')),
                    str(payload.get('completedAt', '')),
                    str(payload.get('requestedBy', 'anonymous')),
                    str(payload.get('exportUrl', '')),
                    safe_int(payload.get('itemCount', 0), default=0),
                    safe_int(payload.get('traceCount', 0), default=0),
                    json.dumps(payload.get('details', {}), ensure_ascii=False),
                ),
            )

    def list(self, *, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        with self.storage.connection() as conn:
            total = int(conn.execute('SELECT COUNT(*) FROM export_job').fetchone()[0])
            rows = conn.execute('SELECT * FROM export_job ORDER BY created_at DESC, job_id DESC LIMIT ? OFFSET ?', (int(limit), int(offset))).fetchall()
        return [self._row_to_export_job(row) for row in rows], total

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.storage.connection() as conn:
            row = conn.execute('SELECT * FROM export_job WHERE job_id=?', (str(job_id),)).fetchone()
        return None if row is None else self._row_to_export_job(row)

    def _row_to_export_job(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            'jobId': str(row['job_id']),
            'batchId': str(row['batch_id']),
            'status': str(row['status']),
            'createdAt': str(row['created_at']),
            'completedAt': str(row['completed_at']),
            'requestedBy': str(row['requested_by']),
            'exportUrl': str(row['export_url']),
            'itemCount': safe_int(row['item_count'], default=0),
            'traceCount': safe_int(row['trace_count'], default=0),
            'details': safe_json_loads(str(row['detail_json']) or '{}'),
        }


@dataclass(slots=True)
class ActionJobStore:
    storage: Any

    def record(self, payload: dict[str, Any]) -> None:
        existing = self.get(str(payload.get('jobId', '')))
        merged = {**(existing or {}), **payload}
        with self.storage.connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO action_job(job_id, kind, status, progress, message, created_at, started_at, completed_at, requested_by, requested_role, cancellable, action_topic, action_type, payload_json, result_json, error_json, feedback_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(merged.get('jobId', '')),
                    str(merged.get('kind', 'generic')),
                    str(merged.get('status', 'QUEUED')),
                    safe_int(merged.get('progress', 0), default=0),
                    str(merged.get('message', '')),
                    str(merged.get('createdAt', '')),
                    str(merged.get('startedAt', '')),
                    str(merged.get('completedAt', '')),
                    str(merged.get('requestedBy', 'anonymous')),
                    str(merged.get('requestedRole', 'viewer')),
                    1 if bool(merged.get('cancellable', True)) else 0,
                    str(merged.get('actionTopic', '')),
                    str(merged.get('actionType', '')),
                    json.dumps(merged.get('payload', {}), ensure_ascii=False),
                    json.dumps(merged.get('result', {}), ensure_ascii=False),
                    json.dumps(merged.get('error', {}), ensure_ascii=False),
                    json.dumps(merged.get('feedback', {}), ensure_ascii=False),
                ),
            )

    def list(self, *, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        with self.storage.connection() as conn:
            total = int(conn.execute('SELECT COUNT(*) FROM action_job').fetchone()[0])
            rows = conn.execute('SELECT * FROM action_job ORDER BY created_at DESC, job_id DESC LIMIT ? OFFSET ?', (int(limit), int(offset))).fetchall()
        return [self._row_to_action_job(row) for row in rows], total

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.storage.connection() as conn:
            row = conn.execute('SELECT * FROM action_job WHERE job_id=?', (str(job_id),)).fetchone()
        return None if row is None else self._row_to_action_job(row)

    def _row_to_action_job(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            'jobId': str(row['job_id']),
            'kind': str(row['kind']),
            'status': str(row['status']),
            'progress': safe_int(row['progress'], default=0),
            'message': str(row['message']),
            'createdAt': str(row['created_at']),
            'startedAt': str(row['started_at']),
            'completedAt': str(row['completed_at']),
            'requestedBy': str(row['requested_by']),
            'requestedRole': str(row['requested_role']),
            'cancellable': bool(safe_int(row['cancellable'], default=0)),
            'actionTopic': str(row['action_topic']),
            'actionType': str(row['action_type']),
            'payload': safe_json_loads(str(row['payload_json']) or '{}'),
            'result': safe_json_loads(str(row['result_json']) or '{}'),
            'error': safe_json_loads(str(row['error_json']) or '{}'),
            'feedback': safe_json_loads(str(row['feedback_json']) or '{}'),
        }
