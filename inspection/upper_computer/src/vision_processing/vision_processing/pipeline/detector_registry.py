from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable

from inspection_utils.vision_common import PluginManifest

from ..plugins.plugin_loader import discover_detector_entry_points, load_manifest_plugins


@dataclass(slots=True)
class DetectorRegistry:
    factories: dict[str, Callable[[], object]] = field(default_factory=dict)
    default_order: list[str] = field(default_factory=list)
    source_map: dict[str, str] = field(default_factory=dict)
    manifests: dict[str, PluginManifest] = field(default_factory=dict)

    def register(self, name: str, factory: Callable[[], object], *, default: bool = True, source: str = 'builtin', manifest: PluginManifest | None = None) -> None:
        self.factories[name] = factory
        self.source_map[name] = source
        if manifest is not None:
            self.manifests[name] = manifest
        if default and name not in self.default_order:
            self.default_order.append(name)

    def register_many(self, entries: dict[str, Callable[[], object]], *, default: bool = False, source: str = 'dynamic') -> None:
        for name, factory in entries.items():
            self.register(name, factory, default=default, source=source, manifest=PluginManifest(kind='detector', name=name, runtime_truth='real' if source != 'manifest' else 'dynamic', source=source))

    def create(self, name: str) -> object:
        if name not in self.factories:
            raise KeyError(f'Unknown detector plugin: {name}')
        return self.factories[name]()

    def discover(self, *, manifest: Iterable[dict] | None = None, entry_point_group: str | None = None) -> dict[str, str]:
        manifest_plugins = load_manifest_plugins(manifest)
        if manifest_plugins:
            self.register_many(manifest_plugins, default=False, source='manifest')
        entry_plugins = discover_detector_entry_points(entry_point_group or 'inspection.vision_detectors')
        if entry_plugins:
            self.register_many(entry_plugins, default=False, source='entry_point')
        return dict(self.source_map)

    def build(self, requested: list[str] | None = None) -> list[object]:
        names = list(requested or self.default_order)
        return [self.create(name) for name in names]

    def manifest_catalog(self) -> list[dict[str, object]]:
        return [manifest.to_dict() for manifest in self.manifests.values()]
