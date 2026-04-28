from __future__ import annotations

from station_bridge.adapter_registry import adapter_manifest_catalog


def test_station_adapter_manifest_catalog_is_derived_from_generated_registry_assets() -> None:
    catalog = {item['name']: item for item in adapter_manifest_catalog()}
    assert set(catalog) >= {'mock', 'serial'}
    assert 'CAPABILITY_QUERY' in catalog['mock']['capabilities']
    assert 'RESET_ACK' in catalog['serial']['capabilities']
    assert 'SERIAL_LINK' in catalog['serial']['capabilities']
    assert 'SYNTHETIC_RUNTIME' in catalog['mock']['capabilities']


def test_station_adapter_manifest_catalog_exposes_capability_profile() -> None:
    catalog = {item['name']: item for item in adapter_manifest_catalog()}
    assert catalog['mock']['capabilityProfile'] == 'simulation_station_default'
    assert catalog['serial']['capabilityProfile'] == 'stm32_station_default'
