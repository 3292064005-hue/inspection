from __future__ import annotations

from copy import deepcopy
from typing import Any


def make_hmi_recipe_payload(
    *,
    recipe_id: str = 'recipe-api',
    name: str = 'API 配方',
    version: str = '1.0.0',
    target_part: str = '测试工件',
    thresholds_summary: str = 'HSV 阈值 + 面积约束 + 二维码 ROI',
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a SaveRecipeRequest-compatible payload for gateway API tests.

    Args:
        recipe_id: Stable recipe identifier written into the request body.
        name: Human-readable recipe name.
        version: Semantic recipe version string.
        target_part: Required target-part descriptor enforced by SaveRecipeRequest.
        thresholds_summary: Required threshold summary enforced by SaveRecipeRequest.
        overrides: Optional field replacements applied last.

    Returns:
        A dictionary accepted by ``POST /api/v1/recipes``.

    Raises:
        ValueError: Any required textual field is empty.
        TypeError: ``overrides`` is supplied but is not a mapping.

    Boundary behavior:
        The helper encodes all current required schema fields so schema drift
        fails at one fixture source instead of scattering stale inline payloads
        across release-gate tests.
    """
    required = {
        'recipe_id': recipe_id,
        'name': name,
        'version': version,
        'target_part': target_part,
        'thresholds_summary': thresholds_summary,
    }
    for key, value in required.items():
        if not str(value or '').strip():
            raise ValueError(f'{key} must not be empty')
    payload: dict[str, Any] = {
        'id': str(recipe_id),
        'name': str(name),
        'version': str(version),
        'targetPart': str(target_part),
        'roi': [1, 2, 3, 4],
        'qrRoi': [5, 6, 7, 8],
        'thresholdsSummary': str(thresholds_summary),
        'sortRules': [
            {'condition': 'score >= 0.80', 'action': 'accept'},
            {'condition': 'score < 0.80', 'action': 'reject'},
        ],
    }
    if overrides is not None:
        if not isinstance(overrides, dict):
            raise TypeError('overrides must be a mapping')
        merged = deepcopy(payload)
        merged.update(overrides)
        payload = merged
    return payload
