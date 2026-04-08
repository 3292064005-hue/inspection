from __future__ import annotations

"""Canonical runtime-contract normalization helpers.

These helpers intentionally sit in ``inspection_utils`` so launch builders,
config validators, and runtime nodes all derive the same effective station
contract before they validate compatibility or instantiate transport adapters.
"""

from typing import Any

from .param_parsing import coerce_bool

_SUPPORTED_ADAPTERS = {"mock", "serial"}


def normalize_protocol_version_label(protocol_version: str | int | None, *, default: str = 'v1') -> str:
    """Normalize a protocol identifier into the canonical ``vN`` form.

    Args:
        protocol_version: Raw protocol identifier supplied by config, manifest,
            firmware, or runtime capability payload.
        default: Canonical fallback used when the value is empty.

    Returns:
        Canonical protocol label such as ``v1`` or ``v2``.

    Raises:
        ValueError: When the payload cannot be interpreted as a supported
            version label.

    Boundary behavior:
        Legacy aliases such as ``1`` and ``1.0`` are accepted and collapsed to
        ``v1`` so compatibility checks and runtime snapshots operate on one
        source of truth.
    """

    if isinstance(protocol_version, int):
        return f"v{max(1, protocol_version)}"
    text = str(protocol_version or '').strip().lower()
    if not text:
        return str(default or 'v1')
    if text.startswith('v') and text[1:].isdigit():
        return f"v{max(1, int(text[1:]))}"
    if text.replace('.', '').isdigit():
        major = int(text.split('.', 1)[0] or '1')
        return f"v{max(1, major)}"
    raise ValueError(f'unsupported_protocol_version:{protocol_version}')


def resolve_protocol_version_number(protocol_version: str | int | None) -> int:
    """Parse one protocol identifier into the bridge-session integer field.

    Args:
        protocol_version: Raw protocol label.

    Returns:
        Positive protocol major version.

    Raises:
        ValueError: When the payload cannot be normalized.
    """

    return int(normalize_protocol_version_label(protocol_version)[1:])


def normalize_adapter_name(adapter_name: str | None, *, sim_mode: bool) -> str:
    """Resolve the effective adapter name for the current runtime mode.

    Args:
        adapter_name: Raw configured adapter name.
        sim_mode: Whether the runtime is operating in simulation mode.

    Returns:
        Canonical adapter name.

    Raises:
        ValueError: When the configured adapter is not supported.

    Boundary behavior:
        Empty adapter names fail closed to ``mock`` during simulation and
        ``serial`` during real-station operation so legacy configs still
        materialize a deterministic transport contract.
    """

    normalized = str(adapter_name or '').strip().lower()
    if not normalized:
        return 'mock' if sim_mode else 'serial'
    if normalized not in _SUPPORTED_ADAPTERS:
        raise ValueError(f'unsupported_station_adapter:{normalized}')
    return normalized


def normalize_station_runtime_config(station_cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Materialize the effective station runtime contract from raw config.

    Args:
        station_cfg: Declarative station configuration payload.

    Returns:
        Normalized station configuration containing canonical ``sim_mode``,
        ``adapter_name``, ``bridge_adapter``, and ``protocol_version`` fields.

    Raises:
        ValueError: When adapter or protocol identifiers are invalid.

    Boundary behavior:
        The returned mapping is a copy, so callers may safely augment it with
        launch-time or runtime-only fields without mutating the original config.
    """

    if not station_cfg:
        return {}
    normalized = dict(station_cfg)
    sim_mode = coerce_bool(normalized.get('sim_mode'), default=False)
    adapter_name = normalize_adapter_name(
        str(normalized.get('adapter_name', normalized.get('bridge_adapter', '')) or ''),
        sim_mode=sim_mode,
    )
    protocol_version = normalize_protocol_version_label(normalized.get('protocol_version', 'v1'))
    normalized['sim_mode'] = sim_mode
    normalized['adapter_name'] = adapter_name
    normalized['bridge_adapter'] = adapter_name
    normalized['protocol_version'] = protocol_version
    return normalized
