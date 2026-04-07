from __future__ import annotations

import os

from .compatibility_validator import load_compatibility_bundle, validate_runtime_bundle
from .profile_resolver import apply_decision_overrides, deep_merge_dicts, load_profile_bundle, normalize_camera_config, normalize_profile_bundle
from .resource_loader import load_yaml


def build_effective_runtime_bundle(
    *,
    recipe_path: str | os.PathLike,
    camera_config_path: str | os.PathLike,
    station_config_path: str | os.PathLike | None = None,
    profile_name: str = 'production',
    profile_config_path: str | os.PathLike | None = None,
    compatibility_path: str | os.PathLike = 'config/compatibility/matrix.yaml',
    resource_package_name: str = 'inspection_utils',
    resource_start: str | os.PathLike | None = None,
) -> dict[str, object]:
    """Build a validated runtime bundle from resolved config resources.

    Args:
        recipe_path: Recipe YAML path.
        camera_config_path: Camera configuration YAML path.
        station_config_path: Optional station YAML path.
        profile_name: Logical runtime profile name.
        profile_config_path: Optional explicit profile path with precedence over the derived profile-name path.
        compatibility_path: Compatibility matrix YAML path.
        resource_package_name: Package name used for relative resource resolution.
        resource_start: Optional source-workspace anchor for resource resolution.

    Returns:
        A mapping containing validated camera, station, recipe, profile, compatibility, and summary payloads.

    Raises:
        FileNotFoundError: When a required YAML resource cannot be found.
        ConfigValidationError: When validation fails.

    Boundary behavior:
        Missing profiles fail closed instead of silently degrading to an empty profile bundle.
    """
    resource_anchor = resource_start or __file__
    recipe = load_yaml(recipe_path, package_name=resource_package_name, start=resource_anchor)
    camera_cfg = normalize_camera_config(load_yaml(camera_config_path, package_name=resource_package_name, start=resource_anchor))
    station_cfg = deep_merge_dicts({}, load_yaml(station_config_path, package_name=resource_package_name, start=resource_anchor)) if station_config_path else {}
    profile_bundle = normalize_profile_bundle(
        load_profile_bundle(profile_name, base_dir='config/profiles', profile_config_path=profile_config_path, package_name=resource_package_name, start=resource_anchor),
        profile_name=profile_name,
    )
    compatibility_bundle = load_compatibility_bundle(compatibility_path, package_name=resource_package_name, start=resource_anchor)
    effective_camera_cfg = normalize_camera_config(deep_merge_dicts(camera_cfg, profile_bundle.get('camera_overrides', {})))
    effective_station_cfg = deep_merge_dicts(station_cfg, profile_bundle.get('station_overrides', {}))
    effective_recipe = apply_decision_overrides(recipe, profile_bundle.get('decision_overrides', {}))
    validated_recipe = validate_runtime_bundle(
        effective_recipe,
        camera_cfg=effective_camera_cfg,
        station_cfg=effective_station_cfg,
        profile_bundle=profile_bundle,
        compatibility_bundle=compatibility_bundle,
    )
    return {
        'profile_bundle': profile_bundle,
        'camera': effective_camera_cfg,
        'station': effective_station_cfg,
        'recipe': validated_recipe,
        'compatibility_bundle': compatibility_bundle,
        'summary': {
            'profile_name': profile_bundle.get('profile_name', profile_name),
            'camera_hz': float(effective_camera_cfg.get('hz', effective_camera_cfg.get('timer_hz', 0.0)) or 0.0),
            'station_adapter': str(effective_station_cfg.get('adapter_name', effective_station_cfg.get('bridge_adapter', '')) or ''),
            'decision_overrides': sorted(str(k) for k in (profile_bundle.get('decision_overrides', {}) or {}).keys()),
        },
    }
