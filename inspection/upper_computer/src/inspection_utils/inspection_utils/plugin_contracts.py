from __future__ import annotations

"""Shared plugin metadata contracts used across detector/provider/adapter registries."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class PluginManifest:
    kind: str
    name: str
    version: str = '1.0'
    capabilities: tuple[str, ...] = ()
    runtime_truth: str = 'real'
    source: str = 'builtin'
    config_schema: dict[str, Any] = field(default_factory=dict)
    capability_profile: str = ''
    owner_plane: str = ''
    verification_requirements: tuple[str, ...] = ()
    promotion_path: tuple[str, ...] = ('synthetic', 'internal', 'production_ready')

    def to_dict(self) -> dict[str, Any]:
        return {
            'kind': self.kind,
            'name': self.name,
            'version': self.version,
            'capabilities': list(self.capabilities),
            'runtimeTruth': self.runtime_truth,
            'source': self.source,
            'configSchema': dict(self.config_schema),
            'capabilityProfile': self.capability_profile,
            'ownerPlane': self.owner_plane,
            'verificationRequirements': list(self.verification_requirements),
            'promotionPath': list(self.promotion_path),
        }
