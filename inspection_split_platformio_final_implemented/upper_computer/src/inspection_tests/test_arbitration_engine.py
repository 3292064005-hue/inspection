from types import SimpleNamespace

from inspection_decision.arbitration_engine import ArbitrationEngine
from inspection_utils.models import DecisionOutcome


def test_arbitration_engine_can_force_recheck_on_low_score_ok():
    engine = ArbitrationEngine({'decision': {'arbitration_low_confidence_threshold': 0.2}, 'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3}})
    result = SimpleNamespace(defect_type='NONE', valid=True, score=0.1)
    outcome = DecisionOutcome(decision='OK', reason='pass', action_code=1, target_bin='OK')
    final = engine.apply(result, outcome)
    assert final.decision == 'RECHECK'
    assert any(note.startswith('arb:score_below') for note in final.arbitration_notes)
