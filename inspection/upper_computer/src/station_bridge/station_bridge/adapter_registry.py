from __future__ import annotations

"""Station adapter factory and protocol-version helpers.

This module turns declarative station configuration into concrete runtime
objects so the bridge node does not silently ignore adapter/protocol settings.
"""

from dataclasses import dataclass, field
from typing import Any, Callable

from inspection_utils.plugin_contracts import PluginManifest

from inspection_utils.runtime_contract import (
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


REGISTRY = StationAdapterRegistry()
REGISTRY.register('mock', lambda **kwargs: MockStationAdapter(kwargs['position_delay_sec'], kwargs['sort_delay_sec']), manifest=PluginManifest(kind='station_adapter', name='mock', capabilities=('SORT_ACK', 'HEARTBEAT'), runtime_truth='synthetic', source='builtin'))
REGISTRY.register('serial', lambda **kwargs: SerialStationAdapter(port=kwargs['serial_port'], baudrate=kwargs['baudrate']), manifest=PluginManifest(kind='station_adapter', name='serial', capabilities=('SORT_ACK', 'HEARTBEAT', 'SERIAL_LINK'), runtime_truth='real', source='builtin'))


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



def build_station_adapter(*, adapter_name: str, position_delay_sec: float, sort_delay_sec: float, serial_port: str, baudrate: int) -> Any:
    """Instantiate the effective station adapter for the current runtime.

    Args:
        adapter_name: Normalized adapter name.
        position_delay_sec: Mock adapter positioning delay.
        sort_delay_sec: Mock adapter sorting delay.
        serial_port: Serial adapter device path.
        baudrate: Serial adapter baudrate.

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
    )
