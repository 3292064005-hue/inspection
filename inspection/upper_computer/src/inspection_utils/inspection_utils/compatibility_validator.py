from __future__ import annotations

import os
from typing import Any

from .compatibility import load_compatibility_matrix, validate_compatibility
from .config_errors import ConfigValidationError
from .resource_loader import load_yaml
from .paths import resolve_resource_path
from .recipe_validator import validate_recipe_config
from .runtime_contract import normalize_station_runtime_config


def load_compatibility_bundle(path: str | os.PathLike = 'config/compatibility/matrix.yaml', *, package_name: str = 'inspection_utils', start: str | os.PathLike | None = None) -> dict[str, Any]:
    resolved = resolve_resource_path(path, package_name=package_name, start=start or __file__)
    if not resolved.exists():
        return load_compatibility_matrix(None).to_dict()
    return load_compatibility_matrix(load_yaml(resolved, package_name=package_name, start=start or __file__)).to_dict()


def validate_runtime_bundle(
    recipe: dict[str, Any],
    camera_cfg: dict[str, Any] | None = None,
    station_cfg: dict[str, Any] | None = None,
    profile_bundle: dict[str, Any] | None = None,
    compatibility_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate one runtime bundle against recipe and compatibility contracts.

    Args:
        recipe: Effective recipe payload.
        camera_cfg: Effective camera configuration.
        station_cfg: Effective or declarative station configuration.
        profile_bundle: Effective profile bundle.
        compatibility_bundle: Compatibility matrix payload.

    Returns:
        Validated recipe payload augmented with compatibility metadata.

    Raises:
        ConfigValidationError: When any recipe/runtime/compatibility contract is violated.

    Boundary behavior:
        Station configuration is normalized into the same effective adapter and
        protocol values used by runtime nodes before compatibility is checked.
    """
    recipe = validate_recipe_config(recipe)
    camera_cfg = camera_cfg or {}
    station_cfg = station_cfg or {}
    profile_bundle = profile_bundle or {}
    compatibility_bundle = compatibility_bundle or load_compatibility_matrix(None).to_dict()
    width = int(camera_cfg.get('width', camera_cfg.get('resolution_width', camera_cfg.get('frame_width', 0))) or 0)
    height = int(camera_cfg.get('height', camera_cfg.get('resolution_height', camera_cfg.get('frame_height', 0))) or 0)
    if width > 0 and height > 0:
        for section_name in ('color', 'qr', 'shape'):
            cfg = recipe.get('vision', {}).get(section_name, {})
            roi = cfg.get('roi') if isinstance(cfg, dict) else None
            if not roi:
                continue
            x = int(roi['x']); y = int(roi['y']); w = int(roi['w']); h = int(roi['h'])
            if x + w > width or y + h > height:
                raise ConfigValidationError(f'vision.{section_name}.roi exceeds camera bounds {width}x{height}')
    supported_profiles = set(recipe.get('metadata', {}).get('supported_profiles', ['production', 'debug', 'maintenance', 'benchmark', 'simulation']))
    profile_name = str(profile_bundle.get('profile_name', 'production'))
    if supported_profiles and profile_name not in supported_profiles:
        raise ConfigValidationError(f'profile {profile_name} is not supported by recipe')
    try:
        normalized_station_cfg = normalize_station_runtime_config(station_cfg if isinstance(station_cfg, dict) else {})
    except ValueError as exc:
        raise ConfigValidationError(str(exc)) from exc
    if normalized_station_cfg:
        sort_mapping = recipe.get('sort_mapping', {})
        supported_bins = normalized_station_cfg.get('supported_action_codes')
        if isinstance(supported_bins, list) and supported_bins:
            supported = {int(v) for v in supported_bins}
            for decision, action_code in sort_mapping.items():
                if int(action_code) not in supported:
                    raise ConfigValidationError(f'sort_mapping.{decision}={action_code} not supported by station')
    matrix = load_compatibility_matrix(compatibility_bundle)
    detector_names = [name for name, cfg in (recipe.get('vision', {}) or {}).items() if isinstance(cfg, dict) and cfg.get('enabled', False)]
    adapter_name = str(normalized_station_cfg.get('adapter_name', normalized_station_cfg.get('bridge_adapter', '')) or '') if isinstance(normalized_station_cfg, dict) else ''
    protocol_version = str(normalized_station_cfg.get('protocol_version', 'v1') or 'v1') if isinstance(normalized_station_cfg, dict) else 'v1'
    compatibility = validate_compatibility(matrix=matrix, profile_name=profile_name, adapter_name=adapter_name, protocol_version=protocol_version, detector_names=detector_names)
    if not compatibility['ok']:
        raise ConfigValidationError('; '.join(compatibility['issues']))
    metadata = recipe.setdefault('metadata', {})
    metadata['runtime_contract'] = {
        'profile_name': profile_name,
        'adapter_name': adapter_name,
        'protocol_version': protocol_version,
        'detectors': list(detector_names),
    }
    warnings = compatibility.get('warnings', [])
    if warnings:
        metadata['compatibility_warnings'] = list(warnings)
    return recipe
