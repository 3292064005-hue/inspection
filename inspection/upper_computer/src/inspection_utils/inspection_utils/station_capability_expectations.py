from __future__ import annotations

"""Helpers for loading generated station capability expectation profiles."""

from dataclasses import dataclass
from typing import Any, Mapping

from .config import load_yaml
from .paths import resolve_resource_path
from .runtime_contract import normalize_protocol_version_label

DEFAULT_STATION_CAPABILITY_EXPECTATIONS_PATH = 'config/system/station_capability_expectations.yaml'


@dataclass(frozen=True, slots=True)
class StationCapabilityExpectation:
    """Normalized station capability expectation derived from the action registry.

    Args:
        profile_name: Registry profile identifier.
        adapter_name: Expected station adapter name.
        protocol_version: Canonical protocol version label.
        features: Required runtime capability feature set.
        supported_action_codes: Required supported action code set.

    Boundary behavior:
        The loader tolerates extra fields in the source YAML. Missing or malformed
        profiles raise :class:`ValueError` so launch/runtime setup fails closed
        instead of accepting silently divergent capability metadata.
    """

    profile_name: str
    adapter_name: str
    protocol_version: str
    features: tuple[str, ...]
    supported_action_codes: tuple[int, ...]

    def to_payload(self, *, firmware_version: str, device_id: str) -> dict[str, Any]:
        """Render one normalized capabilities payload for runtime consumers.

        Args:
            firmware_version: Firmware/runtime identifier placed into the payload.
            device_id: Station device identifier.

        Returns:
            Capability payload compatible with bridge protocol validation.
        """
        return {
            'protocol_version': self.protocol_version,
            'firmware_version': firmware_version,
            'device_id': device_id,
            'features': list(self.features),
            'supported_action_codes': list(self.supported_action_codes),
        }


def _normalize_feature_list(raw_value: object) -> tuple[str, ...]:
    if raw_value in (None, ''):
        return ()
    if not isinstance(raw_value, (list, tuple, set)):
        raise ValueError('station capability features must be a list of strings')
    return tuple(sorted({str(item).strip() for item in raw_value if str(item).strip()}))


def _normalize_action_codes(raw_value: object) -> tuple[int, ...]:
    if raw_value in (None, ''):
        return ()
    if not isinstance(raw_value, (list, tuple, set)):
        raise ValueError('station capability supported_action_codes must be a list of integers')
    return tuple(sorted({int(item) for item in raw_value}))


def _profile_from_payload(profile_name: str, raw_profile: Mapping[str, Any]) -> StationCapabilityExpectation:
    capability = raw_profile.get('firmware_capability_expectation', {}) if isinstance(raw_profile, Mapping) else {}
    if not isinstance(capability, Mapping):
        raise ValueError(f'invalid_station_capability_profile:{profile_name}')
    return StationCapabilityExpectation(
        profile_name=profile_name,
        adapter_name=str(raw_profile.get('adapter_name', 'serial') or 'serial').strip() or 'serial',
        protocol_version=normalize_protocol_version_label(raw_profile.get('protocol_version', 'v1')),
        features=_normalize_feature_list(capability.get('features', ())),
        supported_action_codes=_normalize_action_codes(capability.get('supported_action_codes', ())),
    )


def load_station_capability_expectation(
    profile_name: str,
    *,
    path: str = DEFAULT_STATION_CAPABILITY_EXPECTATIONS_PATH,
    start: str | None = None,
) -> StationCapabilityExpectation:
    """Load one generated station capability expectation profile.

    Args:
        profile_name: Registry profile identifier referenced by station runtime
            configuration.
        path: Runtime-relative path to the generated expectation YAML.
        start: Optional anchor used for resource-path resolution.

    Returns:
        One normalized capability expectation.

    Raises:
        ValueError: When the profile is missing or malformed.

    Boundary behavior:
        Relative paths are resolved through the workspace/share lookup logic so
        both source-workspace and installed deployments consume the same derived
        expectation artifact.
    """
    name = str(profile_name or '').strip()
    if not name:
        raise ValueError('missing_station_capability_profile')
    resolved = resolve_resource_path(path, start=start)
    payload = load_yaml(resolved) if resolved.exists() else {}
    profiles = payload.get('profiles', payload) if isinstance(payload, Mapping) else {}
    if not isinstance(profiles, Mapping):
        raise ValueError('invalid_station_capability_expectations_payload')
    raw_profile = profiles.get(name)
    if not isinstance(raw_profile, Mapping):
        raise ValueError(f'missing_station_capability_profile:{name}')
    return _profile_from_payload(name, raw_profile)


def validate_station_capability_runtime_config(
    *,
    expectation: StationCapabilityExpectation,
    adapter_name: str,
    protocol_version: str,
    supported_action_codes: set[int] | tuple[int, ...] | list[int] | None,
) -> set[int]:
    """Validate runtime station settings against one expectation profile.

    Args:
        expectation: Loaded station capability expectation profile.
        adapter_name: Effective runtime adapter name.
        protocol_version: Effective canonical runtime protocol version.
        supported_action_codes: Runtime configured supported action codes.

    Returns:
        Normalized supported action code set. Empty runtime payloads fall back to
        the expectation-defined action code set.

    Raises:
        ValueError: When adapter name, protocol version, or configured action
            codes diverge from the selected capability profile.

    Boundary behavior:
        Empty configured action-code lists inherit the profile-defined codes so
        older launch payloads can stay concise without weakening fail-closed
        drift detection.
    """
    normalized_adapter = str(adapter_name or '').strip().lower()
    expected_adapter = str(expectation.adapter_name or '').strip().lower()
    if normalized_adapter != expected_adapter:
        raise ValueError(
            'configured adapter_name diverges from station capability profile '
            f'{expectation.profile_name}: {normalized_adapter} != {expected_adapter}'
        )
    normalized_protocol = normalize_protocol_version_label(protocol_version)
    if normalized_protocol != expectation.protocol_version:
        raise ValueError(
            'configured protocol_version diverges from station capability profile '
            f'{expectation.profile_name}: {normalized_protocol} != {expectation.protocol_version}'
        )
    configured_codes = {int(item) for item in (supported_action_codes or [])}
    expected_codes = set(expectation.supported_action_codes)
    if configured_codes and expected_codes and configured_codes != expected_codes:
        raise ValueError(
            'configured supported_action_codes diverge from station capability profile '
            f'{expectation.profile_name}: {sorted(configured_codes)} != {sorted(expected_codes)}'
        )
    return configured_codes or expected_codes
