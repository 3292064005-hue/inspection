from __future__ import annotations

from importlib import import_module, metadata
from typing import Any, Iterable


DEFAULT_ENTRY_POINT_GROUP = 'inspection.vision_detectors'


def _resolve_factory(spec: str):
    module_name, _, attr_name = spec.partition(':')
    if not module_name or not attr_name:
        raise ValueError(f'invalid plugin spec: {spec}')
    module = import_module(module_name)
    factory = getattr(module, attr_name)
    return factory


def discover_detector_entry_points(group: str = DEFAULT_ENTRY_POINT_GROUP) -> dict[str, object]:
    discovered: dict[str, object] = {}
    try:
        entries = metadata.entry_points()
        if hasattr(entries, 'select'):
            candidates = list(entries.select(group=group))
        else:
            candidates = list(entries.get(group, []))
    except Exception:
        candidates = []
    for entry in candidates:
        try:
            discovered[str(entry.name)] = entry.load()
        except Exception:
            continue
    return discovered


def load_manifest_plugins(manifest: Iterable[dict[str, Any]] | None) -> dict[str, object]:
    discovered: dict[str, object] = {}
    for item in manifest or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name', '')).strip()
        spec = str(item.get('factory', '')).strip()
        if not name or not spec:
            continue
        discovered[name] = _resolve_factory(spec)
    return discovered
