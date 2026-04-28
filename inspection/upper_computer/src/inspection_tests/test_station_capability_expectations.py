from __future__ import annotations

from inspection_utils.station_capability_expectations import load_station_capability_expectation, validate_station_capability_runtime_config


def test_load_station_capability_expectation_from_generated_registry_asset() -> None:
    expectation = load_station_capability_expectation('stm32_station_default', start=__file__)

    assert expectation.profile_name == 'stm32_station_default'
    assert expectation.adapter_name == 'serial'
    assert expectation.protocol_version == 'v1'
    assert expectation.features == ('CAPABILITY_QUERY', 'HEARTBEAT', 'RESET_ACK', 'SORT_ACK')
    assert expectation.supported_action_codes == (1, 2, 3)


def test_validate_station_capability_runtime_config_rejects_adapter_name_drift() -> None:
    expectation = load_station_capability_expectation('stm32_station_default', start=__file__)
    try:
        validate_station_capability_runtime_config(
            expectation=expectation,
            adapter_name='mock',
            protocol_version='v1',
            supported_action_codes=[1, 2, 3],
        )
    except ValueError as exc:
        assert 'configured adapter_name diverges from station capability profile' in str(exc)
    else:
        raise AssertionError('expected adapter_name drift failure')


def test_load_simulation_station_capability_expectation_from_generated_registry_asset() -> None:
    expectation = load_station_capability_expectation('simulation_station_default', start=__file__)

    assert expectation.profile_name == 'simulation_station_default'
    assert expectation.adapter_name == 'mock'
    assert expectation.protocol_version == 'v1'
    assert expectation.features == ('CAPABILITY_QUERY', 'HEARTBEAT', 'RESET_ACK', 'SORT_ACK', 'SYNTHETIC_RUNTIME')
    assert expectation.supported_action_codes == (1, 2, 3)
