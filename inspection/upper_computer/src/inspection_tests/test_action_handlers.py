from __future__ import annotations

from inspection_hmi_gateway.action_contract import ACTION_CONTRACTS
from inspection_hmi_gateway.action_handlers import ACTION_HANDLER_REGISTRY


def test_action_handlers_cover_all_registered_contracts() -> None:
    assert set(ACTION_HANDLER_REGISTRY) == set(ACTION_CONTRACTS)
