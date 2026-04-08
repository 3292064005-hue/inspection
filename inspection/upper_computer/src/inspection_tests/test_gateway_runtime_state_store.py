from __future__ import annotations

from inspection_hmi_gateway.state_store import GatewayStateStore


def test_gateway_state_store_mutation_increments_version_and_serves_snapshots() -> None:
    store = GatewayStateStore()
    assert store.version == 0

    store.mutate(lambda state: setattr(state, 'active_recipe_id', 'recipe-1'))
    snapshot = store.snapshot_payload()

    assert store.version == 1
    assert snapshot['activeRecipeId'] == 'recipe-1'

    view = store.view
    view.guidance = 'updated'
    assert store.version == 2
    assert store.snapshot_payload()['guidance'] == 'updated'
