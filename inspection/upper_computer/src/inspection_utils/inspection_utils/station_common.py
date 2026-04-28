from __future__ import annotations

"""Station/protocol boundary exports for gateway and bridge packages."""

from .protocol import (
    CMD_FEED_ONE,
    CMD_HEARTBEAT,
    CMD_QUERY_CAPABILITIES,
    CMD_RESET_FAULT,
    CMD_SORT_TO_BIN,
    Frame,
    FrameStreamParser,
    RSP_ACK,
    RSP_CAPABILITIES,
    RSP_FAULT,
    RSP_HEARTBEAT,
    RSP_NACK,
    RSP_POSITION_READY,
    RSP_SORT_DONE,
)
from .runtime_contract import normalize_adapter_name, normalize_protocol_version_label, resolve_protocol_version_number
from .station_capability_expectations import load_station_capability_expectation, validate_station_capability_runtime_config
from .station_protocol_contract import (
    StationProtocolContractError,
    load_station_protocol_contract,
    validate_capabilities_payload,
    validate_runtime_protocol_version,
)
from .topic_contracts import DECISION_OUTPUT_TOPIC, SORT_REQUEST_LEGACY_TOPIC, SORT_REQUEST_TOPIC

__all__ = [
    'CMD_FEED_ONE',
    'CMD_HEARTBEAT',
    'CMD_QUERY_CAPABILITIES',
    'CMD_RESET_FAULT',
    'CMD_SORT_TO_BIN',
    'DECISION_OUTPUT_TOPIC',
    'Frame',
    'FrameStreamParser',
    'RSP_ACK',
    'RSP_CAPABILITIES',
    'RSP_FAULT',
    'RSP_HEARTBEAT',
    'RSP_NACK',
    'RSP_POSITION_READY',
    'RSP_SORT_DONE',
    'SORT_REQUEST_LEGACY_TOPIC',
    'SORT_REQUEST_TOPIC',
    'StationProtocolContractError',
    'load_station_capability_expectation',
    'load_station_protocol_contract',
    'normalize_adapter_name',
    'normalize_protocol_version_label',
    'resolve_protocol_version_number',
    'validate_capabilities_payload',
    'validate_runtime_protocol_version',
    'validate_station_capability_runtime_config',
]
