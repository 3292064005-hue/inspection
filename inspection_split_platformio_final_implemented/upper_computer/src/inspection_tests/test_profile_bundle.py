from inspection_utils.config import load_profile_bundle, validate_runtime_bundle


def test_load_profile_bundle_reads_debug_profile():
    bundle = load_profile_bundle('debug', base_dir='config/profiles')
    assert bundle['profile_name'] == 'debug'
    assert bundle['decision_overrides']['invalid_to_recheck'] is True


def test_validate_runtime_bundle_rejects_unsupported_profile():
    recipe = {
        'recipe_id': 'r1',
        'metadata': {'supported_profiles': ['production']},
        'vision': {
            'color': {'enabled': True, 'hsv_ranges': {'red': [[0, 0, 0, 1, 1, 1]]}, 'min_ratio': 0.0},
            'shape': {'enabled': False},
            'qr': {'enabled': False},
        },
        'decision': {'expected_color': 'red'},
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }
    try:
        validate_runtime_bundle(recipe, camera_cfg={'frame_width': 640, 'frame_height': 480}, profile_bundle={'profile_name': 'debug'})
    except Exception as exc:
        assert 'not supported' in str(exc)
    else:
        raise AssertionError('expected profile validation to fail')
