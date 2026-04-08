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

    def to_dict(self) -> dict[str, Any]:
        return {
            'kind': self.kind,
            'name': self.name,
            'version': self.version,
            'capabilities': list(self.capabilities),
            'runtimeTruth': self.runtime_truth,
            'source': self.source,
            'configSchema': dict(self.config_schema),
        }
