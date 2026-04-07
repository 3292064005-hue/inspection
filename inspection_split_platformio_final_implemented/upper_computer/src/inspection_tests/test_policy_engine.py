from types import SimpleNamespace

from inspection_decision.policy_engine import apply_policy_overrides
from inspection_utils.models import DecisionOutcome


def test_quality_issue_can_be_rechecked():
    result = SimpleNamespace(defect_type='IMAGE_QUALITY', valid=False, score=0.9)
    outcome = DecisionOutcome(decision='NG', reason='image_quality_issue', action_code=2, target_bin='NG')
    recipe = {'decision': {'recheck_on_quality_issue': True}, 'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3}}
    final = apply_policy_overrides(result, outcome, recipe)
    assert final.decision == 'RECHECK'
    assert 'policy:image_quality_to_recheck' in final.policy_notes
