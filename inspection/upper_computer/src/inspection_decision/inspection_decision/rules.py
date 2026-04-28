from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from inspection_utils.model_common import DecisionOutcome
from inspection_utils.vision_common import PluginManifest


@dataclass(slots=True)
class AttrView:
    source: Any

    def get(self, name: str, default: Any = None) -> Any:
        if hasattr(self.source, name):
            return getattr(self.source, name)
        if isinstance(self.source, dict):
            return self.source.get(name, default)
        return default


@dataclass(slots=True)
class RuleMatch:
    matched: bool
    reason: str


COMPARATORS = {
    'eq': lambda actual, expected: actual == expected,
    'ne': lambda actual, expected: actual != expected,
    'gt': lambda actual, expected: actual > expected,
    'gte': lambda actual, expected: actual >= expected,
    'lt': lambda actual, expected: actual < expected,
    'lte': lambda actual, expected: actual <= expected,
    'in': lambda actual, expected: actual in expected,
    'not_in': lambda actual, expected: actual not in expected,
    'contains': lambda actual, expected: expected in (actual or ''),
}


def _normalize_condition_key(key: str) -> tuple[str, str]:
    for suffix in ('_not_in', '_contains', '_gte', '_lte', '_ne', '_gt', '_lt', '_in'):
        if key.endswith(suffix):
            return key[: -len(suffix)], suffix[1:]
    return key, 'eq'


def _rule_matches(result: Any, when: dict[str, Any]) -> RuleMatch:
    view = AttrView(result)
    explanations: list[str] = []
    for raw_key, expected in when.items():
        field, op = _normalize_condition_key(raw_key)
        actual = view.get(field)
        comparator = COMPARATORS[op]
        if not comparator(actual, expected):
            return RuleMatch(False, f'{field}={actual!r} failed {op} {expected!r}')
        explanations.append(f'{field}={actual!r} {op} {expected!r}')
    return RuleMatch(True, '; '.join(explanations) if explanations else 'fallback rule')


def evaluate_rule_engine(result: Any, recipe: dict) -> DecisionOutcome | None:
    rules_cfg = recipe.get('decision_rules', {})
    rules = list(rules_cfg.get('rules', []))
    if not rules:
        return None

    strategy = str(rules_cfg.get('strategy', 'priority')).lower()
    ordered = sorted(rules, key=lambda item: int(item.get('priority', 0)), reverse=True)
    if strategy == 'first_match':
        ordered = rules

    sort_mapping = recipe.get('sort_mapping', {})
    for rule in ordered:
        match = _rule_matches(result, rule.get('when', {}))
        if not match.matched:
            continue
        then = rule.get('then', {})
        decision = str(then.get('decision', 'NG')).upper()
        target_bin = str(then.get('target_bin', decision))
        action_code = int(then.get('action_code', sort_mapping.get(decision, sort_mapping.get('NG', 2))))
        reason = str(then.get('reason', rule.get('id', 'rule_match')))
        explanation = [f"rule={rule.get('id', 'unnamed')}", match.reason]
        return DecisionOutcome(
            decision=decision,
            reason=reason,
            action_code=action_code,
            target_bin=target_bin,
            matched_rule_id=str(rule.get('id', 'unnamed')),
            matched_rule_priority=int(rule.get('priority', 0)),
            explanation=explanation,
            confidence=float(then.get('confidence', 1.0)),
        )
    return None


def legacy_decide(result: Any, recipe: dict) -> DecisionOutcome:
    target = recipe.get('sort_mapping', {})
    decision_cfg = recipe.get('decision', {})
    color_expect = decision_cfg.get('expected_color')
    allow_recheck_when_qr_fail = bool(decision_cfg.get('recheck_on_qr_fail', True))

    if not getattr(result, 'valid', False):
        return DecisionOutcome('NG', 'invalid_result', int(target.get('NG', 2)), 'NG', 'legacy_invalid', ['result.valid == False'])
    if getattr(result, 'defect_type', 'NONE') not in ('', 'NONE'):
        return DecisionOutcome('NG', result.defect_type, int(target.get('NG', 2)), 'NG', 'legacy_defect', [f"defect_type={getattr(result, 'defect_type', '')}"])
    if color_expect and getattr(result, 'color_name', None) != color_expect:
        return DecisionOutcome('NG', f"color_mismatch:{getattr(result, 'color_name', 'unknown')}", int(target.get('NG', 2)), 'NG', 'legacy_color', [f"expected_color={color_expect}"])
    if not getattr(result, 'orientation_ok', False):
        return DecisionOutcome('NG', 'bad_orientation', int(target.get('NG', 2)), 'NG', 'legacy_orientation', ['orientation_ok == False'])
    if not getattr(result, 'qr_ok', False) and allow_recheck_when_qr_fail:
        return DecisionOutcome('RECHECK', 'qr_fail', int(target.get('RECHECK', 3)), 'RECHECK', 'legacy_qr', ['qr_ok == False'])
    return DecisionOutcome('OK', 'pass', int(target.get('OK', 1)), 'OK', 'legacy_pass', ['legacy fallthrough'])


def decide(result: Any, recipe: dict) -> tuple[str, str, int]:
    outcome = evaluate_rule_engine(result, recipe) or legacy_decide(result, recipe)
    return outcome.decision, outcome.reason, outcome.action_code


def decide_with_trace(result: Any, recipe: dict) -> DecisionOutcome:
    return evaluate_rule_engine(result, recipe) or legacy_decide(result, recipe)



def decision_rule_manifest_catalog() -> list[dict[str, object]]:
    """Return the authoritative decision-rule engine manifest catalog.

    The canonical rule engine and the legacy fallback remain explicit runtime
    capabilities so extension reviews can reason about promotion state without
    reading the decision-node implementation directly.
    """
    manifests = (
        PluginManifest(
            kind='decision_rule_engine',
            name='priority_rule_engine',
            runtime_truth='real',
            source='builtin',
            owner_plane='inspection_decision',
            capabilities=('RULE_ENGINE', 'TRACEABLE_DECISION'),
            verification_requirements=('capture_process_decision_cycle', 'sort_execution_roundtrip'),
        ),
        PluginManifest(
            kind='decision_rule_engine',
            name='legacy_decide_fallback',
            runtime_truth='real',
            source='builtin',
            owner_plane='inspection_decision',
            capabilities=('RULE_ENGINE_FALLBACK',),
            verification_requirements=('capture_process_decision_cycle',),
            promotion_path=('internal', 'production_ready'),
        ),
    )
    return [manifest.to_dict() for manifest in manifests]
