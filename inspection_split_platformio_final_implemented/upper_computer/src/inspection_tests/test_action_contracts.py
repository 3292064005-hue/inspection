from inspection_hmi_gateway.action_contract import action_catalog, validate_action_payload


def test_action_catalog_exposes_topics_and_types() -> None:
    catalog = action_catalog()
    assert any(item['kind'] == 'start_batch' and item['topic'] == '/inspection/actions/start_batch' for item in catalog)


def test_action_payload_validation_uses_contract_requirements() -> None:
    assert validate_action_payload('start_batch', {'recipeId': ''}) == 'recipeId is required'
    assert validate_action_payload('export_batch', {'batchId': 'B1'}) == ''
