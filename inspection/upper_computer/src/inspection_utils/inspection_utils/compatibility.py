from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class CompatibilityError(ValueError):
    pass


@dataclass(slots=True)
class CompatibilityMatrix:
    profiles: dict[str, dict[str, Any]] = field(default_factory=dict)
    adapters: dict[str, dict[str, Any]] = field(default_factory=dict)
    protocol_versions: dict[str, dict[str, Any]] = field(default_factory=dict)
    detectors: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'profiles': dict(self.profiles),
            'adapters': dict(self.adapters),
            'protocol_versions': dict(self.protocol_versions),
            'detectors': dict(self.detectors),
        }


DEFAULT_COMPATIBILITY = CompatibilityMatrix(
    profiles={
        'production': {'allowed_modes': ['AUTO', 'PAUSED']},
        'debug': {'allowed_modes': ['AUTO', 'PAUSED', 'MANUAL_MODE']},
        'maintenance': {'allowed_modes': ['MANUAL_MODE', 'PAUSED']},
        'benchmark': {'allowed_modes': ['AUTO', 'PAUSED', 'BENCHMARK']},
        'simulation': {'allowed_modes': ['AUTO', 'PAUSED', 'MANUAL_MODE']},
    },
    adapters={
        'mock': {'protocol_versions': ['v1', 'v2'], 'supports_profiles': ['debug', 'maintenance', 'benchmark', 'simulation']},
        'serial': {'protocol_versions': ['v1', 'v2'], 'supports_profiles': ['production', 'debug', 'maintenance']},
    },
    protocol_versions={
        'v1': {'allowed_adapters': ['mock', 'serial']},
        'v2': {'allowed_adapters': ['mock', 'serial']},
    },
)


def load_compatibility_matrix(payload: dict[str, Any] | None) -> CompatibilityMatrix:
    if not payload:
        return DEFAULT_COMPATIBILITY
    return CompatibilityMatrix(
        profiles=dict(payload.get('profiles', DEFAULT_COMPATIBILITY.profiles)),
        adapters=dict(payload.get('adapters', DEFAULT_COMPATIBILITY.adapters)),
        protocol_versions=dict(payload.get('protocol_versions', DEFAULT_COMPATIBILITY.protocol_versions)),
        detectors=dict(payload.get('detectors', DEFAULT_COMPATIBILITY.detectors)),
    )



def validate_compatibility(*, matrix: CompatibilityMatrix, profile_name: str, adapter_name: str | None = None, protocol_version: str | None = None, detector_names: list[str] | None = None) -> dict[str, Any]:
    detector_names = list(detector_names or [])
    issues: list[str] = []
    warnings: list[str] = []

    if profile_name not in matrix.profiles:
        issues.append(f'unknown profile: {profile_name}')

    adapter_cfg = matrix.adapters.get(adapter_name or '', {}) if adapter_name else {}
    if adapter_name and not adapter_cfg:
        issues.append(f'unknown adapter: {adapter_name}')

    proto_cfg = matrix.protocol_versions.get(protocol_version or '', {}) if protocol_version else {}
    if protocol_version and not proto_cfg:
        issues.append(f'unknown protocol_version: {protocol_version}')

    if adapter_name and profile_name in matrix.profiles:
        supported_profiles = adapter_cfg.get('supports_profiles') if isinstance(adapter_cfg, dict) else None
        if isinstance(supported_profiles, list) and supported_profiles and profile_name not in supported_profiles:
            issues.append(f'adapter {adapter_name} does not support profile {profile_name}')

    if adapter_name and protocol_version and isinstance(adapter_cfg, dict):
        adapter_protocols = adapter_cfg.get('protocol_versions')
        if isinstance(adapter_protocols, list) and adapter_protocols and protocol_version not in adapter_protocols:
            issues.append(f'adapter {adapter_name} does not support protocol_version {protocol_version}')

    if adapter_name and protocol_version and isinstance(proto_cfg, dict):
        allowed_adapters = proto_cfg.get('allowed_adapters')
        if isinstance(allowed_adapters, list) and allowed_adapters and adapter_name not in allowed_adapters:
            issues.append(f'protocol_version {protocol_version} does not allow adapter {adapter_name}')

    for detector_name in detector_names:
        if detector_name not in matrix.detectors:
            continue
        detector_cfg = matrix.detectors.get(detector_name, {})
        allowed_profiles = detector_cfg.get('supported_profiles') if isinstance(detector_cfg, dict) else None
        if isinstance(allowed_profiles, list) and allowed_profiles and profile_name not in allowed_profiles:
            issues.append(f'detector {detector_name} does not support profile {profile_name}')
        allowed_protocols = detector_cfg.get('protocol_versions') if isinstance(detector_cfg, dict) else None
        if protocol_version and isinstance(allowed_protocols, list) and allowed_protocols and protocol_version not in allowed_protocols:
            warnings.append(f'detector {detector_name} not declared for protocol_version {protocol_version}')

    return {
        'ok': not issues,
        'issues': issues,
        'warnings': warnings,
        'profile_name': profile_name,
        'adapter_name': adapter_name or '',
        'protocol_version': protocol_version or '',
        'detectors': detector_names,
    }
