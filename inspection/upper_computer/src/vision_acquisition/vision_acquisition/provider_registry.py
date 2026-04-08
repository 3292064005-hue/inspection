from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from inspection_utils.plugin_contracts import PluginManifest

from .camera_provider import Esp32HttpCameraProvider, MockCameraProvider, OpenCVCameraProvider


@dataclass(slots=True)
class CameraProviderRegistry:
    factories: dict[str, Callable[..., object]] = field(default_factory=dict)
    manifests: dict[str, PluginManifest] = field(default_factory=dict)

    def register(self, name: str, factory: Callable[..., object], *, manifest: PluginManifest) -> None:
        self.factories[name] = factory
        self.manifests[name] = manifest

    def manifest_catalog(self) -> list[dict[str, object]]:
        return [manifest.to_dict() for manifest in self.manifests.values()]


REGISTRY = CameraProviderRegistry()
REGISTRY.register('mock', MockCameraProvider, manifest=PluginManifest(kind='camera_provider', name='mock', capabilities=('FRAME_SOURCE', 'SYNTHETIC'), runtime_truth='synthetic', source='builtin'))
REGISTRY.register('opencv', OpenCVCameraProvider, manifest=PluginManifest(kind='camera_provider', name='opencv', capabilities=('FRAME_SOURCE', 'USB_CAMERA'), runtime_truth='real', source='builtin'))
REGISTRY.register('esp32_http', Esp32HttpCameraProvider, manifest=PluginManifest(kind='camera_provider', name='esp32_http', capabilities=('FRAME_SOURCE', 'HTTP_SNAPSHOT', 'REMOTE_HEALTH'), runtime_truth='real', source='builtin'))


def provider_manifest_catalog() -> list[dict[str, object]]:
    return REGISTRY.manifest_catalog()
