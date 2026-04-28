from __future__ import annotations

"""Station bridge protocol-contract loading and validation helpers."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .config import load_yaml
from .paths import resolve_runtime_path
from .runtime_contract import normalize_protocol_version_label

DEFAULT_STATION_PROTOCOL_CONTRACT_PATH = 'config/system/station_protocol_contract.yaml'


class StationProtocolContractError(ValueError):
    """Raised when a station protocol payload violates the configured contract."""


@dataclass(frozen=True, slots=True)
class StationProtocolContract:
    accepted_versions: tuple[str, ...]
    compatible_reported_versions: dict[str, tuple[str, ...]]
    capability_required_fields: tuple[str, ...]
    require_supported_action_codes: bool = True
    allow_action_code_superset: bool = True
    heartbeat_version_required: bool = False

    def allowed_reported_versions_for(self, configured_version: str) -> tuple[str, ...]:
        return self.compatible_reported_versions.get(configured_version, (configured_version,))


def load_station_protocol_contract(path: str = DEFAULT_STATION_PROTOCOL_CONTRACT_PATH) -> StationProtocolContract:
    """Load the station protocol contract from configuration."""
    resolved = resolve_runtime_path(path, start=__file__)
    payload = load_yaml(resolved) if resolved.exists() else {}
    protocol = payload.get('protocol', payload) if isinstance(payload, Mapping) else {}
    if not isinstance(protocol, Mapping):
        protocol = {}
    accepted_versions = tuple(normalize_protocol_version_label(item) for item in protocol.get('accepted_versions', ('v1',)))
    compatible: dict[str, tuple[str, ...]] = {}
    raw_compatible = protocol.get('compatible_reported_versions', {})
    if isinstance(raw_compatible, Mapping):
        for configured, versions in raw_compatible.items():
            if isinstance(versions, (list, tuple, set)):
                compatible[normalize_protocol_version_label(configured)] = tuple(normalize_protocol_version_label(item) for item in versions)
    required_fields = tuple(str(item) for item in protocol.get('capability_required_fields', ('protocol_version', 'firmware_version', 'device_id')))
    return StationProtocolContract(
        accepted_versions=accepted_versions,
        compatible_reported_versions=compatible,
        capability_required_fields=required_fields,
        require_supported_action_codes=bool(protocol.get('require_supported_action_codes', True)),
        allow_action_code_superset=bool(protocol.get('allow_action_code_superset', True)),
        heartbeat_version_required=bool(protocol.get('heartbeat_version_required', False)),
    )


def _normalize_action_codes(raw_value: object) -> tuple[int, ...]:
    if raw_value in (None, ''):
        return ()
    if not isinstance(raw_value, (list, tuple, set)):
        raise StationProtocolContractError('supported_action_codes must be a list of integers')
    parsed: list[int] = []
    for item in raw_value:
        parsed.append(int(item))
    return tuple(sorted(set(parsed)))


def _normalize_features(raw_value: object) -> tuple[str, ...]:
    if raw_value in (None, ''):
        return ()
    if not isinstance(raw_value, (list, tuple, set)):
        raise StationProtocolContractError('features must be a list of strings')
    return tuple(sorted({str(item).strip() for item in raw_value if str(item).strip()}))


def validate_capabilities_payload(
    payload: Mapping[str, Any] | None,
    *,
    configured_version: str,
    configured_action_codes: set[int] | tuple[int, ...] | list[int] | None,
    expected_features: Iterable[str] | None = None,
    contract: StationProtocolContract,
) -> dict[str, Any]:
    """Validate a station capabilities payload against the configured runtime contract.

    Args:
        payload: Reported capability payload from the station runtime.
        configured_version: Canonical protocol version configured on the host.
        configured_action_codes: Action codes the host expects the station to support.
        expected_features: Optional station capability feature set derived from the
            single-source station capability profile.
        contract: Loaded protocol-contract rules.

    Returns:
        Normalized capability payload with protocol-contract audit metadata.

    Raises:
        StationProtocolContractError: When required fields, protocol versions,
            action codes, or expected capability features do not match.

    Boundary behavior:
        Extra action codes and features are allowed unless the protocol contract
        forbids code supersets. Missing expected features always fail closed so
        generated station capability expectations become runtime-effective.
    """
    data = dict(payload or {})
    missing = [field for field in contract.capability_required_fields if field not in data or data.get(field) in (None, '', [])]
    if missing:
        raise StationProtocolContractError(f'missing_capability_fields:{",".join(missing)}')
    reported_version = normalize_protocol_version_label(data.get('protocol_version'))
    expected_version = normalize_protocol_version_label(configured_version)
    if reported_version not in contract.accepted_versions:
        raise StationProtocolContractError(f'unsupported_reported_protocol_version:{reported_version}')
    allowed_versions = contract.allowed_reported_versions_for(expected_version)
    if reported_version not in allowed_versions:
        raise StationProtocolContractError(f'incompatible_reported_protocol_version:{expected_version}->{reported_version}')
    normalized_action_codes = _normalize_action_codes(data.get('supported_action_codes', ()))
    normalized_features = _normalize_features(data.get('features', ()))
    if contract.require_supported_action_codes and not normalized_action_codes:
        raise StationProtocolContractError('missing_supported_action_codes')
    configured_codes = set(int(item) for item in (configured_action_codes or []))
    reported_codes = set(normalized_action_codes)
    if configured_codes:
        missing_codes = sorted(configured_codes - reported_codes)
        if missing_codes:
            raise StationProtocolContractError('reported_action_codes_missing:' + ','.join(str(item) for item in missing_codes))
        if not contract.allow_action_code_superset:
            extra_codes = sorted(reported_codes - configured_codes)
            if extra_codes:
                raise StationProtocolContractError('reported_action_codes_extra:' + ','.join(str(item) for item in extra_codes))
    expected_feature_set = {str(item).strip() for item in (expected_features or ()) if str(item).strip()}
    reported_feature_set = set(normalized_features)
    if expected_feature_set:
        missing_features = sorted(expected_feature_set - reported_feature_set)
        if missing_features:
            raise StationProtocolContractError('reported_features_missing:' + ','.join(missing_features))
    normalized = dict(data)
    normalized['protocol_version'] = reported_version
    normalized['features'] = list(normalized_features)
    normalized['supported_action_codes'] = list(normalized_action_codes)
    normalized['protocol_contract'] = {
        'configuredVersion': expected_version,
        'reportedVersion': reported_version,
        'acceptedVersions': list(contract.accepted_versions),
        'allowedReportedVersions': list(allowed_versions),
        'configuredActionCodes': sorted(configured_codes),
        'reportedActionCodes': list(normalized_action_codes),
        'expectedFeatures': sorted(expected_feature_set),
        'reportedFeatures': list(normalized_features),
    }
    return normalized


def validate_runtime_protocol_version(
    payload: Mapping[str, Any] | None,
    *,
    configured_version: str,
    contract: StationProtocolContract,
    required: bool,
) -> dict[str, Any]:
    """Validate a non-capabilities runtime payload carrying optional protocol metadata."""
    data = dict(payload or {})
    expected_version = normalize_protocol_version_label(configured_version)
    raw_version = data.get('protocol_version', '')
    if raw_version in (None, ''):
        if required:
            raise StationProtocolContractError('missing_runtime_protocol_version')
        data.setdefault('protocol_version', expected_version)
        return data
    reported_version = normalize_protocol_version_label(raw_version)
    if reported_version not in contract.accepted_versions:
        raise StationProtocolContractError(f'unsupported_runtime_protocol_version:{reported_version}')
    allowed_versions = contract.allowed_reported_versions_for(expected_version)
    if reported_version not in allowed_versions:
        raise StationProtocolContractError(f'incompatible_runtime_protocol_version:{expected_version}->{reported_version}')
    data['protocol_version'] = reported_version
    return data
