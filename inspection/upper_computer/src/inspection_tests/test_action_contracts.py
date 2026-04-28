from inspection_hmi_gateway.action_contract import action_catalog, ensure_action_submit_allowed, public_action_capability_matrix, validate_action_payload


def test_action_catalog_exposes_topics_types_and_capabilities() -> None:
    catalog = action_catalog()
    start_batch = next(item for item in catalog if item['kind'] == 'start_batch')
    benchmark = next(item for item in catalog if item['kind'] == 'run_benchmark')
    kinds = {item['kind'] for item in catalog}
    assert start_batch['topic'] == '/inspection/actions/start_batch'
    assert start_batch['capability']['availability'] == 'production_ready'
    assert 'run_calibration' not in kinds
    assert benchmark['capability']['availability'] == 'internal_tooling'
    assert benchmark['capability']['generatedClient'] is False
    assert benchmark['capability']['publicCatalog'] is False
    assert benchmark['governance']['tier'] == 'qa_tooling'


def test_action_payload_validation_uses_contract_requirements() -> None:
    assert validate_action_payload('start_batch', {'recipeId': ''}) == 'recipeId is required'
    assert validate_action_payload('export_batch', {'batchId': 'B1'}) == ''


def test_action_submission_policy_rejects_removed_calibration_action() -> None:
    try:
        ensure_action_submit_allowed('run_calibration')
    except KeyError:
        return
    else:  # pragma: no cover - regression guard
        raise AssertionError('run_calibration should be absent from the runtime action surface')


def test_benchmark_submission_policy_is_internal_tooling_and_allowed() -> None:
    contract = ensure_action_submit_allowed('run_benchmark')
    assert contract.kind == 'run_benchmark'
    assert contract.capability.availability == 'internal_tooling'
    assert contract.capability.public_catalog is False


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


def test_action_payload_validation_accepts_boolean_required_fields() -> None:
    assert validate_action_payload('set_maintenance_mode', {'enabled': False}) == ''


def test_action_catalog_includes_promoted_native_first_actions() -> None:
    catalog = {item['kind']: item for item in action_catalog()}
    assert catalog['stop_station']['type'] == 'StopStation'
    assert catalog['set_maintenance_mode']['type'] == 'SetMaintenanceMode'
    assert catalog['create_batch']['type'] == 'CreateBatch'


def test_public_action_capability_matrix_includes_promoted_public_actions() -> None:
    matrix = public_action_capability_matrix()
    assert 'run_calibration' not in matrix
    assert 'run_benchmark' not in matrix
    assert matrix['start_batch']['availability'] == 'production_ready'
