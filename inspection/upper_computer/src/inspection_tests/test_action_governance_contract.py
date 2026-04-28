from inspection_hmi_gateway.action_contract import action_catalog


def test_governance_catalog_marks_promoted_actions_as_official() -> None:
    catalog = {item['kind']: item for item in action_catalog()}
    benchmark = catalog['run_benchmark']
    assert benchmark['governance']['tier'] == 'qa_tooling'
    assert benchmark['governance']['lifecycle'] == 'internal'
    assert benchmark['capability']['deliveryClass'] == 'qa_tooling'
    assert benchmark['capability']['publicCatalog'] is False
    diagnostics = catalog['diagnostic_capture_frame']
    assert diagnostics['governance']['tier'] == 'official'
    assert diagnostics['capability']['deliveryClass'] == 'official'
