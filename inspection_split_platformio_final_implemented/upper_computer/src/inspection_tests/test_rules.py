from inspection_decision.rules import decide, decide_with_trace


class DummyResult:
    valid = True
    defect_type = 'NONE'
    color_name = 'red'
    orientation_ok = True
    qr_ok = True


def test_decide_ok():
    recipe = {
        'decision': {'expected_color': 'red', 'recheck_on_qr_fail': True},
        'decision_rules': {'rules': [{'id': 'default', 'priority': 0, 'when': {}, 'then': {'decision': 'OK', 'reason': 'pass'}}]},
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }
    decision, reason, code = decide(DummyResult(), recipe)
    assert decision == 'OK'
    assert code == 1


def test_decide_recheck_when_qr_fail():
    recipe = {
        'decision': {'expected_color': 'red', 'recheck_on_qr_fail': True},
        'decision_rules': {
            'strategy': 'priority',
            'rules': [
                {'id': 'qr_recheck', 'priority': 10, 'when': {'qr_ok': False, 'defect_type': 'NONE'}, 'then': {'decision': 'RECHECK', 'reason': 'qr_fail'}},
                {'id': 'fallback', 'priority': 0, 'when': {}, 'then': {'decision': 'OK', 'reason': 'pass'}},
            ],
        },
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }
    r = DummyResult()
    r.qr_ok = False
    outcome = decide_with_trace(r, recipe)
    assert outcome.decision == 'RECHECK'
    assert outcome.action_code == 3
    assert outcome.matched_rule_id == 'qr_recheck'


def test_decide_rule_contains_operator():
    recipe = {
        'decision': {'expected_color': 'red', 'recheck_on_qr_fail': True},
        'decision_rules': {
            'strategy': 'priority',
            'rules': [
                {'id': 'contains_check', 'priority': 20, 'when': {'defect_type_contains': 'AREA'}, 'then': {'decision': 'NG', 'reason': 'area_issue'}},
                {'id': 'fallback', 'priority': 0, 'when': {}, 'then': {'decision': 'OK', 'reason': 'pass'}},
            ],
        },
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }
    r = DummyResult()
    r.defect_type = 'AREA_OUT_OF_RANGE'
    outcome = decide_with_trace(r, recipe)
    assert outcome.decision == 'NG'
    assert outcome.reason == 'area_issue'
