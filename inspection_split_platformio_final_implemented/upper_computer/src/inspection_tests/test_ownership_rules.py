from inspection_fsm.ownership_rules import check_binding, check_station_detail


def test_check_binding_accepts_matching_trace_and_item():
    result = check_binding('TRACE-1', 7, {'trace_id': 'TRACE-1', 'item_id': 7})
    assert result.ok is True


def test_check_binding_rejects_mismatched_trace():
    result = check_binding('TRACE-1', 7, {'trace_id': 'TRACE-2', 'item_id': 7})
    assert result.ok is False
    assert 'trace_id_mismatch' in result.reason


def test_check_station_detail_allows_missing_trace_when_active_item_matches():
    result = check_station_detail('TRACE-1', 7, {'item_id': 7})
    assert result.ok is True
