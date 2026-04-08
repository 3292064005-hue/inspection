from __future__ import annotations

from typing import Any

from .config_errors import ConfigValidationError

RECIPE_REQUIRED_TOP_LEVEL = ('recipe_id', 'vision', 'decision', 'sort_mapping')
SUPPORTED_RULE_SUFFIXES = {'', '_ne', '_gt', '_gte', '_lt', '_lte', '_in', '_not_in', '_contains'}
ALLOWED_RULE_FIELDS = {'valid', 'category', 'defect_type', 'score', 'qr_text', 'qr_ok', 'orientation_ok', 'color_name', 'color_ratio'}


def _split_rule_key(raw_key: str) -> tuple[str, str]:
    for suffix in sorted(SUPPORTED_RULE_SUFFIXES - {''}, key=len, reverse=True):
        if raw_key.endswith(suffix):
            return raw_key[:-len(suffix)], suffix
    return raw_key, ''


def _validate_roi(name: str, roi: dict[str, Any]) -> None:
    for key in ('x', 'y', 'w', 'h'):
        if key not in roi:
            raise ConfigValidationError(f'{name}.roi missing key: {key}')
        if int(roi[key]) < 0:
            raise ConfigValidationError(f'{name}.roi.{key} must be >= 0')
    if int(roi['w']) <= 0 or int(roi['h']) <= 0:
        raise ConfigValidationError(f'{name}.roi width/height must be > 0')


def _validate_decision_rules(recipe: dict[str, Any]) -> None:
    if 'decision_rules' not in recipe:
        return
    rules = recipe['decision_rules']
    if not isinstance(rules, dict) or not isinstance(rules.get('rules', []), list):
        raise ConfigValidationError('decision_rules.rules must be a list')
    strategy = str(rules.get('strategy', 'priority')).lower()
    if strategy not in {'priority', 'first_match'}:
        raise ConfigValidationError('decision_rules.strategy must be priority or first_match')
    for idx, rule in enumerate(rules.get('rules', [])):
        if not isinstance(rule, dict):
            raise ConfigValidationError(f'decision_rules.rules[{idx}] must be a mapping')
        when = rule.get('when', {})
        if not isinstance(when, dict):
            raise ConfigValidationError(f'decision_rules.rules[{idx}].when must be a mapping')
        for raw_key in when.keys():
            field, suffix = _split_rule_key(str(raw_key))
            if field not in ALLOWED_RULE_FIELDS or suffix not in SUPPORTED_RULE_SUFFIXES:
                raise ConfigValidationError(f'decision_rules.rules[{idx}].when contains unsupported predicate: {raw_key}')
        outcome = rule.get('then', rule.get('action'))
        if not isinstance(outcome, dict):
            raise ConfigValidationError(f'decision_rules.rules[{idx}].then/action must be a mapping')
        decision = str(outcome.get('decision', '')).strip()
        if not decision:
            raise ConfigValidationError(f'decision_rules.rules[{idx}].then/action.decision must be set')


def validate_recipe_config(recipe: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(recipe, dict):
        raise ConfigValidationError('recipe root must be a mapping')
    for key in RECIPE_REQUIRED_TOP_LEVEL:
        if key not in recipe:
            raise ConfigValidationError(f'missing required top-level key: {key}')
    vision = recipe.get('vision', {})
    if not isinstance(vision, dict):
        raise ConfigValidationError('vision section must be a mapping')
    color_cfg = vision.get('color', {})
    if color_cfg.get('enabled', False):
        if 'roi' in color_cfg:
            _validate_roi('vision.color', color_cfg['roi'])
        min_ratio = float(color_cfg.get('min_ratio', 0.0))
        if not 0.0 <= min_ratio <= 1.0:
            raise ConfigValidationError('vision.color.min_ratio must be within [0.0, 1.0]')
        for color_name, ranges in color_cfg.get('hsv_ranges', {}).items():
            if not isinstance(ranges, list) or not ranges:
                raise ConfigValidationError(f'vision.color.hsv_ranges.{color_name} must be a non-empty list')
            for idx, value_range in enumerate(ranges):
                if not isinstance(value_range, list) or len(value_range) != 6:
                    raise ConfigValidationError(f'vision.color.hsv_ranges.{color_name}[{idx}] must contain 6 values')
    qr_cfg = vision.get('qr', {})
    if qr_cfg.get('enabled', False) and 'roi' in qr_cfg:
        _validate_roi('vision.qr', qr_cfg['roi'])
    shape_cfg = vision.get('shape', {})
    if shape_cfg.get('enabled', False):
        if 'roi' in shape_cfg:
            _validate_roi('vision.shape', shape_cfg['roi'])
        low, high = shape_cfg.get('aspect_ratio_range', [1.0, 99.0])
        if float(low) > float(high):
            raise ConfigValidationError('vision.shape.aspect_ratio_range lower bound exceeds upper bound')
        if float(shape_cfg.get('min_area', 0.0)) > float(shape_cfg.get('max_area', 1e12)):
            raise ConfigValidationError('vision.shape.min_area exceeds max_area')
        thresh = int(shape_cfg.get('binary_thresh', 80))
        if thresh < 0 or thresh > 255:
            raise ConfigValidationError('vision.shape.binary_thresh must be within [0, 255]')
    metadata = recipe.setdefault('metadata', {})
    if isinstance(metadata, dict):
        metadata.setdefault('author', 'unknown')
    else:
        raise ConfigValidationError('metadata section must be a mapping')
    decision = recipe.get('decision', {})
    if not isinstance(decision, dict):
        raise ConfigValidationError('decision section must be a mapping')
    expected_color = decision.get('expected_color')
    if expected_color and color_cfg.get('enabled', False) and expected_color not in color_cfg.get('hsv_ranges', {}):
        raise ConfigValidationError(f'decision.expected_color={expected_color} is not declared in vision.color.hsv_ranges')
    low_conf = float(decision.get('low_confidence_threshold', 0.0))
    if not 0.0 <= low_conf <= 1.0:
        raise ConfigValidationError('decision.low_confidence_threshold must be within [0.0, 1.0]')
    if 'recheck_on_quality_issue' in decision and not isinstance(decision.get('recheck_on_quality_issue'), bool):
        raise ConfigValidationError('decision.recheck_on_quality_issue must be boolean')
    if 'invalid_to_recheck' in decision and not isinstance(decision.get('invalid_to_recheck'), bool):
        raise ConfigValidationError('decision.invalid_to_recheck must be boolean')
    _validate_decision_rules(recipe)
    return recipe
