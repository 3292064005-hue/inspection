from __future__ import annotations

from copy import deepcopy

from inspection_utils.models import DecisionOutcome
from .severity_model import classify_severity


class ArbitrationEngine:
    def __init__(self, recipe: dict) -> None:
        self.recipe = recipe if isinstance(recipe, dict) else {}

    def apply(self, result, outcome: DecisionOutcome) -> DecisionOutcome:
        final = deepcopy(outcome)
        final.severity = classify_severity(
            decision=final.decision,
            defect_type=getattr(result, 'defect_type', ''),
            valid=bool(getattr(result, 'valid', True)),
            score=float(getattr(result, 'score', 0.0)),
        )
        sort_mapping = self.recipe.get('sort_mapping', {})
        confidence_threshold = float(self.recipe.get('decision', {}).get('arbitration_low_confidence_threshold', 0.15))
        if final.severity == 'hard_fail' and final.decision != 'NG':
            final.decision = 'NG'
            final.target_bin = 'NG'
            final.action_code = int(sort_mapping.get('NG', final.action_code))
            final.arbitration_notes.append('arb:hard_fail_forces_ng')
        if float(getattr(result, 'score', 0.0)) < confidence_threshold and final.decision == 'OK':
            final.decision = 'RECHECK'
            final.target_bin = 'RECHECK'
            final.action_code = int(sort_mapping.get('RECHECK', final.action_code))
            final.arbitration_notes.append(f'arb:score_below<{confidence_threshold}')
        if not getattr(result, 'valid', True) and final.decision == 'OK':
            final.decision = 'RECHECK'
            final.target_bin = 'RECHECK'
            final.action_code = int(sort_mapping.get('RECHECK', final.action_code))
            final.arbitration_notes.append('arb:invalid_result_blocks_ok')
        if final.arbitration_notes:
            final.reason = ';'.join([final.reason] + final.arbitration_notes)
        return final
