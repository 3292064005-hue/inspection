from __future__ import annotations

from copy import deepcopy

from inspection_utils.models import DecisionOutcome


def apply_policy_overrides(result, outcome: DecisionOutcome, recipe: dict) -> DecisionOutcome:
    decision_cfg = recipe.get('decision', {}) if isinstance(recipe, dict) else {}
    final = deepcopy(outcome)
    low_conf_threshold = float(decision_cfg.get('low_confidence_threshold', 0.0))
    recheck_on_quality = bool(decision_cfg.get('recheck_on_quality_issue', True))
    invalid_to_recheck = bool(decision_cfg.get('invalid_to_recheck', False))
    sort_mapping = recipe.get('sort_mapping', {}) if isinstance(recipe, dict) else {}

    if getattr(result, 'defect_type', '') == 'IMAGE_QUALITY' and recheck_on_quality and final.decision == 'NG':
        final.decision = 'RECHECK'
        final.target_bin = 'RECHECK'
        final.action_code = int(sort_mapping.get('RECHECK', final.action_code))
        final.policy_notes.append('policy:image_quality_to_recheck')

    if not getattr(result, 'valid', True) and invalid_to_recheck and final.decision == 'NG':
        final.decision = 'RECHECK'
        final.target_bin = 'RECHECK'
        final.action_code = int(sort_mapping.get('RECHECK', final.action_code))
        final.policy_notes.append('policy:invalid_to_recheck')

    score = float(getattr(result, 'score', 0.0))
    if low_conf_threshold > 0.0 and score < low_conf_threshold and final.decision == 'OK':
        final.decision = 'RECHECK'
        final.target_bin = 'RECHECK'
        final.action_code = int(sort_mapping.get('RECHECK', final.action_code))
        final.policy_notes.append(f'policy:low_confidence<{low_conf_threshold}')

    if final.policy_notes:
        final.reason = ';'.join([final.reason] + final.policy_notes)
    return final
