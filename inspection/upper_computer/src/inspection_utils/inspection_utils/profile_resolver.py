from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

from .config_errors import ConfigValidationError
from .resource_loader import load_yaml
from .paths import resolve_resource_path

CONFIG_SECTION_DEFAULTS: dict[str, dict[str, Any]] = {'camera': {'hz': 5.0}, 'station': {}, 'decision': {}}
CAMERA_ALIASES = {'timer_hz': 'hz'}


def deep_merge_dicts(base: Mapping[str, Any] | None, overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(dict(base or {}))
    for key, value in dict(overrides or {}).items():
        current = result.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            result[key] = deep_merge_dicts(current, value)
        else:
            result[key] = deepcopy(value)
    return result


def _canonicalize_aliases(data: Mapping[str, Any], aliases: Mapping[str, str]) -> dict[str, Any]:
    payload = dict(data)
    for legacy_key, canonical_key in aliases.items():
        if canonical_key not in payload and legacy_key in payload:
            payload[canonical_key] = payload[legacy_key]
    return payload


def normalize_camera_config(data: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = deep_merge_dicts(CONFIG_SECTION_DEFAULTS['camera'], _canonicalize_aliases(data or {}, CAMERA_ALIASES))
    if 'hz' in payload:
        payload['hz'] = float(payload['hz'])
        payload.setdefault('timer_hz', payload['hz'])
    elif 'timer_hz' in payload:
        payload['timer_hz'] = float(payload['timer_hz'])
        payload['hz'] = payload['timer_hz']
    return payload


def normalize_profile_bundle(bundle: Mapping[str, Any] | None, *, profile_name: str) -> dict[str, Any]:
    payload = deep_merge_dicts({}, bundle or {})
    payload.setdefault('profile_name', profile_name)
    payload['camera_overrides'] = normalize_camera_config(payload.get('camera_overrides', {}))
    payload['station_overrides'] = deep_merge_dicts(CONFIG_SECTION_DEFAULTS['station'], payload.get('station_overrides', {}))
    payload['decision_overrides'] = deep_merge_dicts(CONFIG_SECTION_DEFAULTS['decision'], payload.get('decision_overrides', {}))
    return payload


def apply_decision_overrides(recipe: Mapping[str, Any], decision_overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    effective_recipe = deep_merge_dicts({}, recipe)
    effective_recipe['decision'] = deep_merge_dicts(effective_recipe.get('decision', {}), decision_overrides or {})
    return effective_recipe


def load_profile_bundle(
    profile_name: str,
    base_dir: str | os.PathLike = 'config/profiles',
    *,
    profile_config_path: str | os.PathLike | None = None,
    package_name: str = 'inspection_utils',
    start: str | os.PathLike | None = None,
) -> dict[str, Any]:
    normalized_profile_path = None if profile_config_path is None or not str(profile_config_path).strip() else Path(str(profile_config_path).strip())
    candidate = normalized_profile_path if normalized_profile_path is not None else Path(base_dir) / f'{profile_name}.yaml'
    path = resolve_resource_path(candidate, package_name=package_name, start=start or __file__)
    if not path.exists():
        raise ConfigValidationError(f'profile bundle not found for profile={profile_name}: {path}')
    return normalize_profile_bundle(load_yaml(path, package_name=package_name, start=start or __file__), profile_name=profile_name)
