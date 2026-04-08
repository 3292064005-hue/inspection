from __future__ import annotations

from dataclasses import dataclass
from typing import Any

LEVEL_MAP = {'OK': 0, 'WARN': 1, 'WARNING': 1, 'ERROR': 2, 'STALE': 3}


@dataclass(slots=True)
class DiagnosticStatusLike:
    name: str
    level: int
    message: str
    values: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            'name': self.name,
            'level': self.level,
            'message': self.message,
            'values': dict(self.values),
        }



def snapshot_to_statuses(snapshot: dict[str, Any], *, prefix: str = 'inspection') -> list[dict[str, Any]]:
    channels = snapshot.get('channels', {}) if isinstance(snapshot, dict) else {}
    statuses: list[dict[str, Any]] = []
    for name, payload in sorted(channels.items()):
        if not isinstance(payload, dict):
            continue
        level = LEVEL_MAP.get(str(payload.get('level', 'OK')).upper(), 3)
        status = DiagnosticStatusLike(
            name=f'{prefix}/{name}',
            level=level,
            message=str(payload.get('message', '')),
            values=dict(payload.get('values', {}) if isinstance(payload.get('values', {}), dict) else {}),
        )
        statuses.append(status.to_dict())
    overall_level = LEVEL_MAP.get(str(snapshot.get('overall_level', 'OK')).upper(), 3)
    statuses.insert(
        0,
        DiagnosticStatusLike(
            name=f'{prefix}/overall',
            level=overall_level,
            message=str(snapshot.get('summary', '')),
            values={'channel_count': len(statuses)},
        ).to_dict(),
    )
    return statuses
