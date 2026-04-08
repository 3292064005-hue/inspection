from inspection_hmi_gateway.action_contract import ActionPolicyError, action_catalog, ensure_action_submit_allowed, validate_action_payload


def test_action_catalog_exposes_topics_types_and_capabilities() -> None:
    catalog = action_catalog()
    start_batch = next(item for item in catalog if item['kind'] == 'start_batch')
    calibration = next(item for item in catalog if item['kind'] == 'run_calibration')
    benchmark = next(item for item in catalog if item['kind'] == 'run_benchmark')
    assert start_batch['topic'] == '/inspection/actions/start_batch'
    assert start_batch['capability']['availability'] == 'production_ready'
    assert calibration['capability']['submitEnabled'] is False
    assert calibration['capability']['submitReason'] == 'calibration_workflow_not_available'
    assert benchmark['capability']['availability'] == 'synthetic'


def test_action_payload_validation_uses_contract_requirements() -> None:
    assert validate_action_payload('start_batch', {'recipeId': ''}) == 'recipeId is required'
    assert validate_action_payload('export_batch', {'batchId': 'B1'}) == ''


def test_action_submission_policy_rejects_disabled_calibration() -> None:
    try:
        ensure_action_submit_allowed('run_calibration')
    except ActionPolicyError as exc:
        assert exc.reason == 'calibration_workflow_not_available'
    else:  # pragma: no cover - regression guard
        raise AssertionError('run_calibration should be blocked by policy')


def test_benchmark_submission_policy_requires_explicit_environment_gate(monkeypatch) -> None:
    monkeypatch.delenv('INSPECTION_EXPERIMENTAL_ACTIONS_ENABLED', raising=False)
    try:
        ensure_action_submit_allowed('run_benchmark')
    except ActionPolicyError as exc:
        assert exc.reason == 'benchmark_requires_experimental_actions'
    else:  # pragma: no cover - regression guard
        raise AssertionError('run_benchmark should be blocked without env gate')

    monkeypatch.setenv('INSPECTION_EXPERIMENTAL_ACTIONS_ENABLED', '1')
    contract = ensure_action_submit_allowed('run_benchmark')
    assert contract.kind == 'run_benchmark'


class _Runtime:
    def health(self) -> dict:
        return {
            'runtimeReady': True,
            'actionExecution': {
                'transportMode': 'executor_bridge',
                'transportReady': True,
                'transportObserved': True,
                'actionExecutorExpected': True,
                'nativeActionClientEnabled': False,
                'executorUpdateChannelBound': True,
                'receivedExecutorUpdates': 1,
            },
        }


class _Context:
    runtime = _Runtime()


def test_action_query_service_catalog_includes_runtime_deployment_metadata() -> None:
    from inspection_hmi_gateway.server.query_services import ActionQueryService

    catalog = ActionQueryService(_Context()).catalog()
    start_batch = next(item for item in catalog if item['kind'] == 'start_batch')
    assert start_batch['deployment']['transportMode'] == 'executor_bridge'
    assert start_batch['deployment']['transportReady'] is True
    assert start_batch['deployment']['transportObserved'] is True


def test_action_catalog_can_hide_non_production_actions_from_default_public_discovery() -> None:
    catalog = action_catalog(include_non_production=False)
    kinds = {item['kind'] for item in catalog}
    assert 'start_batch' in kinds
    assert 'run_calibration' not in kinds
    assert 'run_benchmark' not in kinds
