from __future__ import annotations

import json
from pathlib import Path

from inspection_hmi_gateway.recipe_store import RecipeStore


def _sample_recipe(recipe_id: str) -> dict:
    return {
        'recipe_id': recipe_id,
        'version': '1.0.0',
        'metadata': {
            'author': 'tester',
            'display_name': recipe_id,
            'target_part': 'part',
            'notes': 'note',
            'updated_at': '2026-03-31T08:00:00Z',
        },
        'vision': {
            'color': {'enabled': True, 'roi': {'x': 1, 'y': 2, 'w': 3, 'h': 4}},
            'qr': {'enabled': False, 'roi': {'x': 5, 'y': 6, 'w': 7, 'h': 8}},
        },
        'decision': {'expected_color': 'red'},
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }


def test_activate_writes_receipt_and_snapshots(tmp_path: Path) -> None:
    store = RecipeStore(tmp_path)
    store.save_from_hmi({
        'id': 'recipe-a',
        'name': '配方A',
        'version': '1.2.3',
        'updatedBy': 'alice',
        'targetPart': '零件A',
        'roi': [10, 11, 12, 13],
        'qrRoi': [20, 21, 22, 23],
    })

    receipt = store.activate('recipe-a', operator='alice')

    assert receipt['recipeId'] == 'recipe-a'
    active = store.current_default()
    assert active['recipe_id'] == 'recipe-a'
    assert (tmp_path / '.state' / 'current' / 'active_recipe.yaml').exists()
    activation_files = list((tmp_path / '.state' / 'activations').glob('*.json'))
    assert activation_files, 'activation receipt should be written'
    payload = json.loads(activation_files[0].read_text(encoding='utf-8'))
    assert payload['recipeId'] == 'recipe-a'
    assert list((tmp_path / '.state' / 'revisions').glob('*-recipe-a-activate.yaml'))


def test_save_from_hmi_persists_recipe_profile(tmp_path: Path) -> None:
    store = RecipeStore(tmp_path)
    recipe = store.save_from_hmi({
        'id': 'recipe-b',
        'name': '配方B',
        'version': '2.0.0',
        'updatedBy': 'bob',
        'targetPart': '零件B',
        'changeNote': '调整ROI',
        'roi': [1, 2, 30, 40],
        'qrRoi': [5, 6, 7, 8],
        'sortRules': [{'condition': 'decision == OK', 'action': 'BOX_OK'}],
    })

    assert recipe['recipe_id'] == 'recipe-b'
    saved = store.load_by_id('recipe-b')
    assert saved is not None
    assert saved['vision']['color']['roi'] == {'x': 1, 'y': 2, 'w': 30, 'h': 40}
    assert saved['metadata']['author'] == 'bob'
    assert list((tmp_path / '.state' / 'revisions').glob('*-recipe-b-save.yaml'))



def test_activate_receipt_uses_next_run_semantics(tmp_path: Path) -> None:
    store = RecipeStore(tmp_path)
    store.save_from_hmi({'id': 'recipe-next', 'name': '配方 next', 'version': '3.0.0', 'updatedBy': 'alice', 'targetPart': '零件', 'roi': [1, 2, 3, 4], 'qrRoi': [5, 6, 7, 8]})

    receipt = store.activate('recipe-next', operator='alice')

    assert receipt['recipeId'] == 'recipe-next'
    assert receipt['recipeVersion'] == '3.0.0'
    assert receipt['activationMode'] == 'NEXT_RUN'
    assert receipt['activationState'] == 'PENDING_START'
    assert receipt['effectiveOn'] == 'next_start'
    assert receipt['runtimeAcknowledged'] is False
    assert receipt['configGeneration']
    assert store.current_activation()['activationId'] == receipt['activationId']


def test_mark_activation_start_requested_updates_receipt_in_place(tmp_path: Path) -> None:
    store = RecipeStore(tmp_path)
    store.save_from_hmi({'id': 'recipe-start', 'name': '配方 start', 'version': '1.0.0', 'updatedBy': 'bob', 'targetPart': '零件', 'roi': [0, 0, 10, 10], 'qrRoi': [0, 0, 0, 0]})
    receipt = store.activate('recipe-start', operator='bob')

    updated = store.mark_activation_start_requested(recipe_id='recipe-start', batch_id='BATCH-42')

    assert updated['activationId'] == receipt['activationId']
    assert updated['activationState'] == 'START_REQUESTED'
    assert updated['appliedBatchId'] == 'BATCH-42'
    assert updated['appliedAt']
    assert store.current_activation()['activationState'] == 'START_REQUESTED'


def test_preflight_start_request_detects_default_snapshot_mismatch(tmp_path: Path) -> None:
    store = RecipeStore(tmp_path)
    store.save_from_hmi({'id': 'recipe-a', 'name': '配方A', 'version': '1.0.0', 'updatedBy': 'alice', 'targetPart': '零件A', 'roi': [0, 0, 10, 10], 'qrRoi': [0, 0, 0, 0]})
    store.save_from_hmi({'id': 'recipe-b', 'name': '配方B', 'version': '1.0.0', 'updatedBy': 'alice', 'targetPart': '零件B', 'roi': [0, 0, 10, 10], 'qrRoi': [0, 0, 0, 0]})
    store.activate('recipe-a', operator='alice')
    store._save_yaml_atomic(store.default_recipe_path, store.load_by_id('recipe-b'))

    try:
        store.preflight_start_request(recipe_id='recipe-a', batch_id='BATCH-1')
    except Exception as exc:
        assert 'default recipe snapshot does not match requested recipe' in str(exc)
    else:
        raise AssertionError('preflight should reject diverged default recipe snapshot')


def test_mark_runtime_acknowledged_updates_current_receipt(tmp_path: Path) -> None:
    store = RecipeStore(tmp_path)
    store.save_from_hmi({'id': 'recipe-runtime', 'name': '配方 runtime', 'version': '4.0.0', 'updatedBy': 'alice', 'targetPart': '零件', 'roi': [1, 2, 3, 4], 'qrRoi': [5, 6, 7, 8]})
    store.activate('recipe-runtime', operator='alice')
    store.mark_activation_start_requested(recipe_id='recipe-runtime', batch_id='BATCH-9')

    updated = store.mark_runtime_acknowledged(recipe_id='recipe-runtime', observed_at='2026-04-02T12:00:00Z', batch_id='BATCH-9', recipe_version='4.0.0')

    assert updated['activationState'] == 'RUNTIME_ACKNOWLEDGED'
    assert updated['runtimeAcknowledged'] is True
    assert updated['runtimeAcknowledgedAt'] == '2026-04-02T12:00:00Z'
    assert updated['runtimeObservedBatchId'] == 'BATCH-9'
    assert store.current_activation()['activationState'] == 'RUNTIME_ACKNOWLEDGED'
