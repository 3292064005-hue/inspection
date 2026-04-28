from __future__ import annotations

"""Station adapter factory and protocol-version helpers.

This module turns declarative station configuration into concrete runtime
objects so the bridge node does not silently ignore adapter/protocol settings.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from inspection_utils.config_common import load_yaml
from inspection_utils.io_common import resolve_resource_path
from inspection_utils.vision_common import PluginManifest

from inspection_utils.station_common import (
    normalize_adapter_name as normalize_station_adapter_name,
    normalize_protocol_version_label,
    resolve_protocol_version_number as resolve_station_protocol_version_number,
)

from .mock_adapter import MockStationAdapter
from .serial_adapter import SerialStationAdapter


@dataclass(slots=True)
class StationAdapterRegistry:
    factories: dict[str, Callable[..., Any]] = field(default_factory=dict)
    manifests: dict[str, PluginManifest] = field(default_factory=dict)

    def register(self, name: str, factory: Callable[..., Any], *, manifest: PluginManifest) -> None:
        self.factories[name] = factory
        self.manifests[name] = manifest

    def build(self, name: str, **kwargs: Any) -> Any:
        if name not in self.factories:
            raise ValueError(f'unsupported_station_adapter:{name}')
        return self.factories[name](**kwargs)

    def manifest_catalog(self) -> list[dict[str, object]]:
        return [manifest.to_dict() for manifest in self.manifests.values()]

DEFAULT_STATION_ADAPTER_MANIFEST_PATH = 'config/system/station_adapter_manifests.yaml'


def _load_station_adapter_manifest_catalog(*, path: str = DEFAULT_STATION_ADAPTER_MANIFEST_PATH, start: str | None = None) -> dict[str, PluginManifest]:
    resolved = resolve_resource_path(path, start=start or __file__)
    payload = load_yaml(resolved) if resolved.exists() else {}
    raw_adapters = payload.get('adapters', payload) if isinstance(payload, dict) else {}
    if not isinstance(raw_adapters, dict):
        raise ValueError('station adapter manifest payload must be a mapping')
    manifests: dict[str, PluginManifest] = {}
    for raw_name, raw_manifest in raw_adapters.items():
        name = str(raw_name or '').strip()
        if not name or not isinstance(raw_manifest, dict):
            continue
        manifests[name] = PluginManifest(
            kind='station_adapter',
            name=name,
            capabilities=tuple(str(item).strip() for item in raw_manifest.get('capabilities', ()) if str(item).strip()),
            runtime_truth=str(raw_manifest.get('runtime_truth', raw_manifest.get('runtimeTruth', 'real')) or 'real'),
            source=str(raw_manifest.get('source', 'generated') or 'generated'),
            capability_profile=str(raw_manifest.get('capability_profile', raw_manifest.get('capabilityProfile', '')) or ''),
            owner_plane='station_bridge',
            verification_requirements=tuple(str(item).strip() for item in raw_manifest.get('verification_requirements', raw_manifest.get('verificationRequirements', ())) if str(item).strip()),
            promotion_path=tuple(str(item).strip() for item in raw_manifest.get('promotion_path', raw_manifest.get('promotionPath', ('synthetic', 'internal', 'production_ready'))) if str(item).strip()),
        )
    if not manifests:
        raise ValueError('station adapter manifest catalog resolved to an empty set')
    return manifests


REGISTRY = StationAdapterRegistry()
_STATION_ADAPTER_MANIFESTS = _load_station_adapter_manifest_catalog(start=__file__)
REGISTRY.register('mock', lambda **kwargs: MockStationAdapter(kwargs['position_delay_sec'], kwargs['sort_delay_sec'], capability_payload=kwargs.get('capability_payload')), manifest=_STATION_ADAPTER_MANIFESTS['mock'])
REGISTRY.register('serial', lambda **kwargs: SerialStationAdapter(port=kwargs['serial_port'], baudrate=kwargs['baudrate']), manifest=_STATION_ADAPTER_MANIFESTS['serial'])


def adapter_manifest_catalog() -> list[dict[str, object]]:
    return REGISTRY.manifest_catalog()


def normalize_adapter_name(adapter_name: str | None, *, sim_mode: bool) -> str:
    """Return the effective adapter name for the current runtime.

    Args:
        adapter_name: Requested adapter name from runtime configuration.
        sim_mode: Whether the bridge is running in simulation mode.

    Returns:
        Normalized adapter name.

    Raises:
        ValueError: When the requested adapter is unknown.

    Boundary behavior:
        Empty adapter names fall back to ``mock`` in simulation and ``serial``
        in real mode so older launch payloads remain compatible.
    """
    return normalize_station_adapter_name(adapter_name, sim_mode=sim_mode)



def canonical_protocol_version(protocol_version: str | int | None) -> str:
    """Normalize one protocol identifier into the canonical bridge label.

    Args:
        protocol_version: Declarative or runtime protocol identifier.

    Returns:
        Canonical ``vN`` label.

    Raises:
        ValueError: When the protocol identifier is unsupported.
    """
    return normalize_protocol_version_label(protocol_version)



def resolve_protocol_version_number(protocol_version: str | int | None) -> int:
    """Parse a protocol-version label into the bridge session integer field."""
    return resolve_station_protocol_version_number(protocol_version)



def build_station_adapter(*, adapter_name: str, position_delay_sec: float, sort_delay_sec: float, serial_port: str, baudrate: int, capability_payload: dict[str, Any] | None = None) -> Any:
    """Instantiate the effective station adapter for the current runtime.

    Args:
        adapter_name: Normalized adapter name.
        position_delay_sec: Mock adapter positioning delay.
        sort_delay_sec: Mock adapter sorting delay.
        serial_port: Serial adapter device path.
        baudrate: Serial adapter baudrate.
        capability_payload: Optional derived capability payload forwarded to
            adapters that can emulate or report capabilities.

    Returns:
        Concrete adapter instance implementing the bridge callback contract.

    Raises:
        ValueError: When the adapter name is unsupported.
        RuntimeError: Propagated from the serial adapter when pyserial or the
            device path is unavailable.
    """
    return REGISTRY.build(
        adapter_name,
        position_delay_sec=position_delay_sec,
        sort_delay_sec=sort_delay_sec,
        serial_port=serial_port,
        baudrate=baudrate,
        capability_payload=capability_payload,
    )
