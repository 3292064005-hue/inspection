from __future__ import annotations

from types import SimpleNamespace

from inspection_hmi_gateway.action_workflows import switch_recipe_workflow


class _RecipeStore:
    def __init__(self) -> None:
        self.preflight_calls: list[tuple[str, str]] = []
        self.candidate_calls: list[tuple[str, str, str]] = []

    def load_by_id(self, recipe_id: str):
        return {'recipe_id': recipe_id, 'version': '2.0.0'}

    def _config_generation(self, recipe: dict[str, object]) -> str:
        return 'cfg-gen'

    def current_default(self):
        return {'recipe_id': 'default-recipe'}

    def current_activation(self):
        return {'activationState': 'PENDING_START'}

    def validate_activation_candidate(self, *, recipe_id: str, batch_id: str, operator: str):
        self.candidate_calls.append((recipe_id, batch_id, operator))
        return {
            'recipeId': recipe_id,
            'batchId': batch_id,
            'configGeneration': 'cfg-gen',
            'activation': {'activationState': 'PENDING_START'},
            'preflight': {
                'executed': True,
                'valid': True,
                'message': 'staged candidate ok',
                'configGeneration': 'cfg-gen',
            },
            'stateMutated': False,
        }

    def preflight_start_request(self, *, recipe_id: str, batch_id: str):
        self.preflight_calls.append((recipe_id, batch_id))
        return {'batchId': batch_id, 'activation': {'activationState': 'READY_TO_START'}}


class _App:
    def __init__(self) -> None:
        self.recipe_store = _RecipeStore()
        self.state = SimpleNamespace(active_recipe_id='active-recipe')
        self.activation_calls: list[tuple[str, str]] = []

    def activate_recipe(self, recipe_id: str, *, operator: str):
        self.activation_calls.append((recipe_id, operator))
        return {'activationState': 'PENDING_START', 'recipeId': recipe_id}


def test_switch_recipe_with_validation_dry_run_reports_staged_preflight_without_mutation() -> None:
    app = _App()
    sink: dict[str, object] = {}
    for step in switch_recipe_workflow(app=app, recipe_id='recipe-1', dry_run=True, actor='tester', result_sink=sink):
        if step.perform:
            step.perform()

    validation = sink['validation']
    assert validation['recipeSnapshotValid'] is True
    assert validation['startContractValid'] is True
    assert validation['validationCompleted'] is True
    assert validation['valid'] is True
    assert validation['preflight']['executed'] is True
    assert validation['stateMutated'] is False
    assert app.recipe_store.candidate_calls == [('recipe-1', 'VALIDATION-PREVIEW', 'tester')]
    assert app.recipe_store.preflight_calls == []
    assert app.activation_calls == []


def test_switch_recipe_with_validation_post_activation_reports_completed_preflight() -> None:
    app = _App()
    sink: dict[str, object] = {}
    for step in switch_recipe_workflow(app=app, recipe_id='recipe-2', dry_run=False, actor='tester', result_sink=sink):
        if step.perform:
            step.perform()

    validation = sink['validation']
    assert validation['recipeSnapshotValid'] is True
    assert validation['startContractValid'] is True
    assert validation['validationCompleted'] is True
    assert validation['valid'] is True
    assert validation['preflight']['executed'] is True
    assert validation['stateMutated'] is True
    assert app.recipe_store.candidate_calls == [('recipe-2', 'VALIDATION-PREVIEW', 'tester')]
    assert app.recipe_store.preflight_calls == []
    assert app.activation_calls == [('recipe-2', 'tester')]
