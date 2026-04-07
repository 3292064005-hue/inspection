from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StationCapabilities:
    protocol_version: str = '1.0'
    firmware_version: str = 'mock'
    device_id: str = 'station'
    features: set[str] = field(default_factory=set)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> 'StationCapabilities':
        data = payload or {}
        return cls(
            protocol_version=str(data.get('protocol_version', '1.0')),
            firmware_version=str(data.get('firmware_version', 'unknown')),
            device_id=str(data.get('device_id', 'station')),
            features={str(x) for x in data.get('features', [])},
        )

    def supports(self, feature: str) -> bool:
        return feature in self.features

    def to_dict(self) -> dict[str, Any]:
        return {
            'protocol_version': self.protocol_version,
            'firmware_version': self.firmware_version,
            'device_id': self.device_id,
            'features': sorted(self.features),
        }
