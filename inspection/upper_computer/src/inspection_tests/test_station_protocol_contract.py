from __future__ import annotations

from inspection_utils.station_protocol_contract import (
    StationProtocolContract,
    StationProtocolContractError,
    validate_capabilities_payload,
    validate_runtime_protocol_version,
)


def _contract() -> StationProtocolContract:
    return StationProtocolContract(
        accepted_versions=('v1',),
        compatible_reported_versions={'v1': ('v1',)},
        capability_required_fields=('protocol_version', 'firmware_version', 'device_id', 'supported_action_codes'),
        require_supported_action_codes=True,
        allow_action_code_superset=True,
        heartbeat_version_required=False,
    )


def test_validate_capabilities_payload_rejects_missing_configured_action_codes() -> None:
    try:
        validate_capabilities_payload(
            {
                'protocol_version': 'v1',
                'firmware_version': 'fw',
                'device_id': 'dev-1',
                'supported_action_codes': [1],
            },
            configured_version='v1',
            configured_action_codes={1, 2},
            contract=_contract(),
        )
    except StationProtocolContractError as exc:
        assert 'reported_action_codes_missing:2' in str(exc)
    else:
        raise AssertionError('expected protocol contract validation failure')


def test_validate_runtime_protocol_version_accepts_compatible_payload() -> None:
    payload = validate_runtime_protocol_version({'protocol_version': '1.0'}, configured_version='v1', contract=_contract(), required=False)
    assert payload['protocol_version'] == 'v1'


def test_validate_capabilities_payload_rejects_missing_expected_features() -> None:
    try:
        validate_capabilities_payload(
            {
                'protocol_version': 'v1',
                'firmware_version': 'fw',
                'device_id': 'dev-1',
                'features': ['SORT_ACK', 'HEARTBEAT'],
                'supported_action_codes': [1, 2],
            },
            configured_version='v1',
            configured_action_codes={1, 2},
            expected_features={'SORT_ACK', 'HEARTBEAT', 'RESET_ACK'},
            contract=_contract(),
        )
    except StationProtocolContractError as exc:
        assert 'reported_features_missing:RESET_ACK' in str(exc)
    else:
        raise AssertionError('expected protocol contract validation failure')


def test_validate_capabilities_payload_accepts_expected_features_superset() -> None:
    payload = validate_capabilities_payload(
        {
            'protocol_version': 'v1',
            'firmware_version': 'fw',
            'device_id': 'dev-1',
            'features': ['SORT_ACK', 'HEARTBEAT', 'RESET_ACK', 'CAPABILITY_QUERY'],
            'supported_action_codes': [1, 2],
        },
        configured_version='v1',
        configured_action_codes={1, 2},
        expected_features={'SORT_ACK', 'HEARTBEAT', 'RESET_ACK'},
        contract=_contract(),
    )
    assert payload['protocol_contract']['expectedFeatures'] == ['HEARTBEAT', 'RESET_ACK', 'SORT_ACK']
    assert payload['protocol_contract']['reportedFeatures'] == ['CAPABILITY_QUERY', 'HEARTBEAT', 'RESET_ACK', 'SORT_ACK']
