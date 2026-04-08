from __future__ import annotations

"""Explicit read-model maintenance coordination.

The SQLite projection remains the canonical query surface, but repair work is a
maintenance concern. This module persists maintenance status and serializes
repair operations so query handlers can surface accurate status without running
full rebuild work inline.
"""

import json
from pathlib import Path
from threading import Lock
from typing import Any

from .runtime_components import utc_now


class ReadModelMaintenanceCoordinator:
    """Serialize and persist gateway read-model repair state."""

    def __init__(self, *, log_root: str | Path, repository: Any, policy: Any) -> None:
        self.log_root = Path(log_root)
        self.repository = repository
        self.policy = policy
        self.status_path = self.log_root / 'results' / 'read_model_maintenance_status.json'
        self._lock = Lock()
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.status_path.exists():
            self._write_status({'maintenanceState': 'IDLE', 'repairRunning': False, 'lastError': '', 'lastRepairAt': '', 'lastReason': ''})

    def _read_status(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.status_path.read_text(encoding='utf-8'))
        except Exception:
            return {'maintenanceState': 'IDLE', 'repairRunning': False, 'lastError': '', 'lastRepairAt': '', 'lastReason': ''}
        return payload if isinstance(payload, dict) else {'maintenanceState': 'IDLE', 'repairRunning': False, 'lastError': '', 'lastRepairAt': '', 'lastReason': ''}

    def _write_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            'maintenanceState': str(payload.get('maintenanceState', 'IDLE')),
            'repairRunning': bool(payload.get('repairRunning', False)),
            'lastError': str(payload.get('lastError', '')),
            'lastRepairAt': str(payload.get('lastRepairAt', '')),
            'lastReason': str(payload.get('lastReason', '')),
        }
        self.status_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
        return normalized

    def status(self, *, readiness: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = self._read_status()
        if readiness:
            payload.update(
                {
                    'projectionAvailable': bool(readiness.get('projectionAvailable')),
                    'repairRequired': bool(readiness.get('repairRequired')),
                    'sourceSyncToken': str(readiness.get('sourceSyncToken', '')),
                    'materializedSyncToken': str(readiness.get('materializedSyncToken', '')),
                }
            )
        return payload

    def bootstrap_if_needed(self) -> dict[str, Any]:
        """Perform bootstrap repair on empty projections outside the query path."""
        if not bool(getattr(self.policy, 'bootstrap_repair_on_empty_db', False)):
            return self.status(readiness=self.repository.readiness())
        if self.repository.has_projection_data():
            return self.status(readiness=self.repository.readiness())
        return self.repair(reason='bootstrap_empty_projection')

    def repair(self, *, reason: str = 'explicit_repair') -> dict[str, Any]:
        """Run one serialized projection repair and persist maintenance status."""
        with self._lock:
            self._write_status({'maintenanceState': 'RUNNING', 'repairRunning': True, 'lastError': '', 'lastRepairAt': '', 'lastReason': reason})
            try:
                self.repository.repair()
                readiness = self.repository.readiness()
                payload = self._write_status(
                    {
                        'maintenanceState': 'IDLE',
                        'repairRunning': False,
                        'lastError': '',
                        'lastRepairAt': utc_now(),
                        'lastReason': reason,
                    }
                )
                payload.update(self.status(readiness=readiness))
                return payload
            except Exception as exc:
                readiness = self.repository.readiness()
                payload = self._write_status(
                    {
                        'maintenanceState': 'FAILED',
                        'repairRunning': False,
                        'lastError': str(exc),
                        'lastRepairAt': '',
                        'lastReason': reason,
                    }
                )
                payload.update(self.status(readiness=readiness))
                raise
