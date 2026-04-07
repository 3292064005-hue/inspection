from __future__ import annotations

"""Focused repository facades for gateway metadata persistence.

The historical ``MetadataRepository`` remains the storage entrypoint, while
these facades provide narrower responsibility boundaries for audit/session/export
and action-job access patterns.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AuditRepository:
    storage: Any

    def append(self, payload: dict[str, Any]) -> None:
        self.storage.append_audit(payload)

    def list(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return self.storage.list_audit(limit=limit, offset=offset)


@dataclass(slots=True)
class SessionRepository:
    storage: Any

    def upsert(self, payload: dict[str, Any]) -> None:
        self.storage.upsert_session(payload)

    def deactivate(self, token: str) -> None:
        self.storage.deactivate_session(token)

    def get_active(self, token: str) -> dict[str, Any] | None:
        return self.storage.get_active_session(token)


@dataclass(slots=True)
class ExportJobRepository:
    storage: Any

    def record(self, payload: dict[str, Any]) -> None:
        self.storage.record_export_job(payload)

    def list(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return self.storage.list_export_jobs(limit=limit, offset=offset)

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self.storage.get_export_job(job_id)


@dataclass(slots=True)
class ActionJobRepository:
    storage: Any

    def record(self, payload: dict[str, Any]) -> None:
        self.storage.record_action_job(payload)

    def list(self, *, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
        return self.storage.list_action_jobs(limit=limit, offset=offset)

    def get(self, job_id: str) -> dict[str, Any] | None:
        return self.storage.get_action_job(job_id)
