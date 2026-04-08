import pytest

from inspection_utils.config import ConfigValidationError, validate_recipe_config, validate_runtime_bundle


def test_validate_recipe_allows_contains_rule_suffix():
    recipe = {
        'recipe_id': 'demo',
        'vision': {
            'color': {
                'enabled': True,
                'hsv_ranges': {'red': [[0, 0, 0, 1, 1, 1]]},
                'min_ratio': 0.1,
            }
        },
        'decision': {'expected_color': 'red'},
        'decision_rules': {
            'rules': [
                {
                    'id': 'contains',
                    'when': {'defect_type_contains': 'AREA'},
                    'then': {'decision': 'NG', 'reason': 'bad'},
                }
            ]
        },
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }
    validated = validate_recipe_config(recipe)
    assert validated['metadata']['author'] == 'unknown'


def test_validate_recipe_expected_color_must_exist_in_color_ranges():
    recipe = {
        'recipe_id': 'demo',
        'vision': {
            'color': {
                'enabled': True,
                'hsv_ranges': {'blue': [[0, 0, 0, 1, 1, 1]]},
                'min_ratio': 0.1,
            }
        },
        'decision': {'expected_color': 'red'},
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }
    with pytest.raises(ConfigValidationError):
        validate_recipe_config(recipe)


def test_validate_recipe_rejects_unknown_rule_field():
    recipe = {
        'recipe_id': 'demo',
        'vision': {'color': {'enabled': False}},
        'decision': {},
        'decision_rules': {
            'rules': [
                {
                    'id': 'bad_field',
                    'when': {'color_typo_ne': 'red'},
                    'then': {'decision': 'NG', 'reason': 'bad'},
                }
            ]
        },
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }
    with pytest.raises(ConfigValidationError):
        validate_recipe_config(recipe)


def test_validate_runtime_bundle_rejects_roi_out_of_bounds():
    recipe = {
        'recipe_id': 'demo',
        'vision': {
            'color': {
                'enabled': True,
                'roi': {'x': 0, 'y': 0, 'w': 1000, 'h': 20},
                'hsv_ranges': {'red': [[0, 0, 0, 1, 1, 1]]},
                'min_ratio': 0.1,
            }
        },
        'decision': {'expected_color': 'red'},
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }
    with pytest.raises(ConfigValidationError):
        validate_runtime_bundle(recipe, camera_cfg={'frame_width': 640, 'frame_height': 480})
