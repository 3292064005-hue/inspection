from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from inspection_utils.runtime_contract import normalize_protocol_version_label


@dataclass(slots=True)
class StationCapabilities:
    protocol_version: str = 'v1'
    firmware_version: str = 'mock'
    device_id: str = 'station'
    features: set[str] = field(default_factory=set)
    supported_action_codes: tuple[int, ...] = ()

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> 'StationCapabilities':
        """Build one capability snapshot from a station payload.

        Args:
            payload: Parsed capability payload from bridge runtime or station
                firmware.

        Returns:
            Normalized capability snapshot.

        Raises:
            No exception is raised for malformed action-code entries. Invalid
            protocol labels fall back to ``v1`` to keep diagnostics readable.

        Boundary behavior:
            Action codes that cannot be interpreted as integers are ignored
            instead of poisoning the full capability payload.
        """
        data = payload or {}
        raw_action_codes = data.get('supported_action_codes', [])
        supported_action_codes: list[int] = []
        if isinstance(raw_action_codes, (list, tuple, set)):
            for item in raw_action_codes:
                try:
                    supported_action_codes.append(int(item))
                except (TypeError, ValueError):
                    continue
        try:
            protocol_version = normalize_protocol_version_label(data.get('protocol_version', 'v1'))
        except ValueError:
            protocol_version = 'v1'
        return cls(
            protocol_version=protocol_version,
            firmware_version=str(data.get('firmware_version', 'unknown')),
            device_id=str(data.get('device_id', 'station')),
            features={str(x) for x in data.get('features', [])},
            supported_action_codes=tuple(sorted(set(supported_action_codes))),
        )

    def supports(self, feature: str) -> bool:
        return feature in self.features

    def to_dict(self) -> dict[str, Any]:
        return {
            'protocol_version': self.protocol_version,
            'firmware_version': self.firmware_version,
            'device_id': self.device_id,
            'features': sorted(self.features),
            'supported_action_codes': list(self.supported_action_codes),
        }
