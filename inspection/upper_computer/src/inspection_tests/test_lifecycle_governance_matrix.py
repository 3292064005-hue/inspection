from inspection_utils.lifecycle_matrix import allows_lifecycle_fallback, governed_node_names, lifecycle_governance_for, lifecycle_governance_matrix


def test_lifecycle_governance_matrix_contains_expected_nodes():
    matrix = lifecycle_governance_matrix()
    assert any(item['node'] == 'inspection_supervisor_node' for item in matrix)
    assert any(item['governanceClass'] == 'native_required' for item in matrix)
    supervisor = lifecycle_governance_for('inspection_supervisor_node')
    assert supervisor is not None
    assert supervisor['governanceClass'] == 'standard_node'
    assert supervisor['lifecycleManaged'] is False
    assert supervisor['supervisorMonitored'] is False
    assert 'inspection_hmi_gateway_server' in governed_node_names()
    gateway = lifecycle_governance_for('inspection_hmi_gateway_node')
    assert gateway is not None
    assert gateway['lifecycleMode'] == 'external_service'
    assert gateway['lifecycleManaged'] is False
    assert gateway['supervisorMonitored'] is False


def test_standard_nodes_do_not_allow_topic_lifecycle_fallback():
    hmi = lifecycle_governance_for('inspection_hmi_node')
    assert hmi is not None
    assert hmi['governanceClass'] == 'standard_node'
    assert allows_lifecycle_fallback('inspection_hmi_node') is False
