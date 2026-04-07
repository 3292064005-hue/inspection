from inspection_utils.lifecycle_matrix import allows_lifecycle_fallback, governed_node_names, lifecycle_governance_for, lifecycle_governance_matrix


def test_lifecycle_governance_matrix_contains_expected_nodes():
    matrix = lifecycle_governance_matrix()
    assert any(item['node'] == 'inspection_supervisor_node' for item in matrix)
    assert any(item['governanceClass'] == 'native_required' for item in matrix)
    assert 'inspection_hmi_gateway_node' in governed_node_names()
    gateway = lifecycle_governance_for('inspection_hmi_gateway_node')
    assert gateway is not None
    assert gateway['lifecycleMode'] == 'managed_runtime'


def test_standard_nodes_do_not_allow_topic_lifecycle_fallback():
    hmi = lifecycle_governance_for('inspection_hmi_node')
    assert hmi is not None
    assert hmi['governanceClass'] == 'standard_node'
    assert allows_lifecycle_fallback('inspection_hmi_node') is False
