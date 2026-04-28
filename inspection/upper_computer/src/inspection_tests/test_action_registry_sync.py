from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from sync_action_registry import render_all  # noqa: E402


def test_action_registry_derived_assets_are_current() -> None:
    expected = render_all()
    for path, rendered in expected.items():
        assert path.read_text(encoding='utf-8') == rendered, path


def test_station_profile_derives_host_and_firmware_assets() -> None:
    expected = render_all()
    station_yaml = next(text for path, text in expected.items() if path.name == 'station_stm32.yaml')
    codes_header = next(text for path, text in expected.items() if path.name == 'inspection_station_action_codes_generated.hpp')
    profile_header = next(text for path, text in expected.items() if path.name == 'inspection_station_action_profile.h')
    manifest_yaml = next(text for path, text in expected.items() if path.name == 'station_adapter_manifests.yaml')
    features_header = next(text for path, text in expected.items() if path.name == 'inspection_station_capability_features_generated.hpp')
    assert 'station_capability_profile: stm32_station_default' in station_yaml
    assert 'supported_action_codes:' in station_yaml
    assert 'INSPECTION_ACTION_CODE_SORT_OK' in codes_header
    assert 'serial:' in manifest_yaml
    assert 'simulation_station_default' in manifest_yaml
    assert 'SERIAL_LINK' in manifest_yaml
    assert 'capability_features()' in features_header
    assert 'INSPECTION_STATION_ACTION_ROUTES' in profile_header
