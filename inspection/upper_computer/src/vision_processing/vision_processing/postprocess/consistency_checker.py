from __future__ import annotations

from typing import Any


def apply_consistency_checks(context, recipe: dict) -> list[str]:
    issues: list[str] = []
    outputs = getattr(context, 'outputs', {}) or {}
    evidence = getattr(context, 'evidence', {}) or {}
    color_cfg = recipe.get('vision', {}).get('color', {}) if isinstance(recipe, dict) else {}
    known_colors = set((color_cfg.get('hsv_ranges') or {}).keys())

    if outputs.get('qr_ok') and not outputs.get('qr_text'):
        issues.append('blocking:qr_text_missing')

    color_name = str(outputs.get('color_name', 'unknown'))
    if color_name not in {'unknown', ''} and known_colors and color_name not in known_colors:
        issues.append(f'blocking:unknown_color_name:{color_name}')

    detectors = evidence.get('detectors', {}) if isinstance(evidence, dict) else {}
    if outputs.get('orientation_ok') is True and str(outputs.get('defect_type', 'NONE')).upper() not in {'', 'NONE'}:
        shape_evidence = detectors.get('shape', {}) if isinstance(detectors, dict) else {}
        if shape_evidence.get('status') == 'OK':
            issues.append('warning:defect_orientation_mismatch')

    if outputs.get('qr_ok') and not detectors.get('qr', {}).get('overlay_refs') and not outputs.get('qr_text'):
        issues.append('warning:qr_missing_overlay')

    return issues
