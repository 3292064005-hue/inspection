import pytest

from inspection_utils.compatibility import load_compatibility_matrix, validate_compatibility
from inspection_utils.config import ConfigValidationError, load_compatibility_bundle, validate_runtime_bundle


def _recipe():
    return {
        'recipe_id': 'r1',
        'metadata': {'supported_profiles': ['production', 'debug']},
        'vision': {
            'color': {'enabled': True, 'roi': {'x': 0, 'y': 0, 'w': 10, 'h': 10}, 'hsv_ranges': {'red': [[0, 0, 0, 10, 10, 10]]}, 'min_ratio': 0.1},
            'qr': {'enabled': False},
            'shape': {'enabled': False},
        },
        'decision': {'expected_color': 'red'},
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }


def test_validate_compatibility_flags_unknown_adapter():
    matrix = load_compatibility_matrix(None)
    result = validate_compatibility(matrix=matrix, profile_name='production', adapter_name='unknown', protocol_version='v1')
    assert not result['ok']
    assert 'unknown adapter' in result['issues'][0]


def test_validate_runtime_bundle_checks_compatibility_bundle():
    with pytest.raises(ConfigValidationError):
        validate_runtime_bundle(
            _recipe(),
            camera_cfg={'width': 100, 'height': 100},
            station_cfg={'adapter_name': 'mock', 'protocol_version': 'v1'},
            profile_bundle={'profile_name': 'production'},
            compatibility_bundle=load_compatibility_bundle(),
        )
