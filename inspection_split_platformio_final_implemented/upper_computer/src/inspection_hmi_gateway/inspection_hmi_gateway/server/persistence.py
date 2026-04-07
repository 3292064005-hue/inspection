from __future__ import annotations

"""Compatibility façade for gateway metadata persistence.

Historical callers still import ``MetadataRepository`` and table helpers from
this module. Internally, SQLite lifecycle/schema management and table-focused
access now live in dedicated modules.
"""

from pathlib import Path
from typing import Any

from .metadata_components import ActionJobRepository, AuditRepository, ExportJobRepository, SessionRepository
from .metadata_database import MetadataSqliteStore, safe_int as _safe_int, token_digest
from .metadata_table_access import ActionJobStore, AuditLogStore, ExportJobStore, SessionStore


class MetadataRepository(MetadataSqliteStore):
    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        self._audit_store = AuditLogStore(self)
        self._session_store = SessionStore(self)
        self._export_store = ExportJobStore(self)
        self._action_store = ActionJobStore(self)
        self.audit_repository = AuditRepository(self)
        self.session_repository = SessionRepository(self)
        self.export_job_repository = ExportJobRepository(self)
        self.action_job_repository = ActionJobRepository(self)

    def append_audit(self, payload: dict[str, Any]) -> None:
        self._audit_store.append(payload)

    def list_audit(self, *, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self._audit_store.list(limit=limit, offset=offset)

    def upsert_session(self, payload: dict[str, Any]) -> None:
        self._session_store.upsert(payload)

    def deactivate_session(self, token: str) -> None:
        self._session_store.deactivate(token)

    def get_active_session(self, token: str) -> dict[str, Any] | None:
        return self._session_store.get_active(token)

    def record_export_job(self, payload: dict[str, Any]) -> None:
        self._export_store.record(payload)

    def list_export_jobs(self, *, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self._export_store.list(limit=limit, offset=offset)

    def get_export_job(self, job_id: str) -> dict[str, Any] | None:
        return self._export_store.get(job_id)

    def record_action_job(self, payload: dict[str, Any]) -> None:
        self._action_store.record(payload)

    def list_action_jobs(self, *, limit: int = 100, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self._action_store.list(limit=limit, offset=offset)

    def get_action_job(self, job_id: str) -> dict[str, Any] | None:
        return self._action_store.get(job_id)
