from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ChannelStatus:
    level: str = 'OK'
    message: str = ''
    values: dict[str, Any] = field(default_factory=dict)

    def snapshot(self) -> dict[str, Any]:
        return {'level': self.level, 'message': self.message, 'values': dict(self.values)}


@dataclass(slots=True)
class DiagnosticsSnapshot:
    overall_level: str = 'OK'
    summary: str = 'healthy'
    channels: dict[str, ChannelStatus] = field(default_factory=dict)

    def set_channel(self, name: str, level: str, message: str, **values: Any) -> None:
        self.channels[name] = ChannelStatus(level=level, message=message, values=values)

    def to_dict(self) -> dict[str, Any]:
        return {
            'overall_level': self.overall_level,
            'summary': self.summary,
            'channels': {name: status.snapshot() for name, status in sorted(self.channels.items())},
        }
