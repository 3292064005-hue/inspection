from inspection_utils.qos import qos_compatibility_warnings, qos_policy_matrix, qos_summary


def test_qos_summary_contains_expected_profiles():
    summary = qos_summary()
    assert summary['sensor_data']['reliability'] == 'BEST_EFFORT'
    assert summary['result']['reliability'] == 'RELIABLE'
    assert summary['event']['depth'] >= 20
    assert summary['diagnostics']['durability'] == 'TRANSIENT_LOCAL'
    assert summary['control']['liveliness'] == 'MANUAL_BY_TOPIC'


def test_qos_policy_matrix_and_compatibility_warnings():
    matrix = qos_policy_matrix()
    assert any(item['name'] == 'lifecycle' for item in matrix)
    warnings = qos_compatibility_warnings(publisher='sensor_data', subscriber='result')
    assert 'publisher_best_effort_to_reliable_subscriber' in warnings
