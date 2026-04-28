from __future__ import annotations

"""Shared contract exports for higher-level packages.

The repository historically imported contract helpers from several utility
modules. This boundary keeps those imports stable while narrowing callers to a
small, explicit surface.
"""

from .plugin_contracts import PluginContract, load_plugin_contract
from .station_capability_expectations import (
    DEFAULT_STATION_CAPABILITY_EXPECTATIONS_PATH,
    StationCapabilityExpectation,
    load_station_capability_expectation,
)
from .station_protocol_contract import (
    DEFAULT_STATION_PROTOCOL_CONTRACT_PATH,
    ProtocolContractError,
    StationProtocolContract,
    load_station_protocol_contract,
)
from .topic_contracts import TopicContract, topic_contract, topic_contract_matrix
from .transport_contracts import (
    TransportEnvelope,
    decode_transport_message,
    encode_transport_message,
)

__all__ = [
    'DEFAULT_STATION_CAPABILITY_EXPECTATIONS_PATH',
    'DEFAULT_STATION_PROTOCOL_CONTRACT_PATH',
    'PluginContract',
    'ProtocolContractError',
    'StationCapabilityExpectation',
    'StationProtocolContract',
    'TopicContract',
    'TransportEnvelope',
    'decode_transport_message',
    'encode_transport_message',
    'load_plugin_contract',
    'load_station_capability_expectation',
    'load_station_protocol_contract',
    'topic_contract',
    'topic_contract_matrix',
]
