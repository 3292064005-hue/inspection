import pytest
from pathlib import Path
from inspection_utils.config import build_effective_runtime_bundle, load_profile_bundle

def test_load_profile_bundle_normalizes_legacy_camera_aliases() -> None:
    payload = load_profile_bundle('debug')
    assert payload['camera_overrides']['hz'] == 3.0
    assert payload['camera_overrides']['timer_hz'] == 3.0

def test_build_effective_runtime_bundle_applies_profile_overrides() -> None:
    root = Path(__file__).resolve().parents[2]
    bundle = build_effective_runtime_bundle(recipe_path=root / 'config' / 'recipes' / 'default_recipe.yaml', camera_config_path=root / 'config' / 'camera' / 'camera.yaml', station_config_path=root / 'config' / 'station' / 'station.yaml', profile_name='benchmark', compatibility_path=root / 'config' / 'compatibility' / 'matrix.yaml')
    assert bundle['camera']['hz'] == 8.0
    assert bundle['camera']['timer_hz'] == 8.0
    assert bundle['recipe']['decision']['low_confidence_threshold'] == 0.2
    assert bundle['summary']['profile_name'] == 'benchmark'


def test_build_effective_runtime_bundle_accepts_explicit_profile_path() -> None:
    root = Path(__file__).resolve().parents[2]
    bundle = build_effective_runtime_bundle(
        recipe_path=root / 'config' / 'recipes' / 'default_recipe.yaml',
        camera_config_path=root / 'config' / 'camera' / 'camera.yaml',
        station_config_path=root / 'config' / 'station' / 'station.yaml',
        profile_name='benchmark',
        profile_config_path=root / 'config' / 'profiles' / 'benchmark.yaml',
        compatibility_path=root / 'config' / 'compatibility' / 'matrix.yaml',
    )
    assert bundle['summary']['profile_name'] == 'benchmark'


def test_load_profile_bundle_raises_when_missing() -> None:
    with pytest.raises(Exception):
        load_profile_bundle('missing_profile_for_contract_test')


def test_blank_profile_path_falls_back_to_profile_name() -> None:
    root = Path(__file__).resolve().parents[2]
    bundle = build_effective_runtime_bundle(
        recipe_path=root / 'config' / 'recipes' / 'default_recipe.yaml',
        camera_config_path=root / 'config' / 'camera' / 'camera.yaml',
        station_config_path=root / 'config' / 'station' / 'station.yaml',
        profile_name='benchmark',
        profile_config_path='',
        compatibility_path=root / 'config' / 'compatibility' / 'matrix.yaml',
    )
    assert bundle['profile_bundle']['profile_name'] == 'benchmark'


def test_build_effective_runtime_bundle_materializes_station_runtime_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    bundle = build_effective_runtime_bundle(
        recipe_path=root / 'config' / 'recipes' / 'default_recipe.yaml',
        camera_config_path=root / 'config' / 'camera' / 'camera.yaml',
        station_config_path=root / 'config' / 'station' / 'station.yaml',
        profile_name='simulation',
        compatibility_path=root / 'config' / 'compatibility' / 'matrix.yaml',
    )
    assert bundle['station']['adapter_name'] == 'mock'
    assert bundle['station']['protocol_version'] == 'v1'
    assert bundle['summary']['station_adapter'] == 'mock'
    assert bundle['summary']['station_protocol_version'] == 'v1'
