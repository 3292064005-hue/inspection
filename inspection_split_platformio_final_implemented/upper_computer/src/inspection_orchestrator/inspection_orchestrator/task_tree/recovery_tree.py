from __future__ import annotations

from inspection_orchestrator.bt import Action, Condition, Selector, Sequence


def _translate(plan: list[dict[str, object]]) -> list[dict[str, object]]:
    translated: list[dict[str, object]] = []
    for step in plan:
        action = str(step.get('action', 'noop'))
        if action == 'pause_auto':
            translated.append({'action': 'pause'})
        elif action == 'request_reset_if_faulted':
            translated.append({'action': 'reset_fault'})
    return translated or [{'action': 'noop'}]


def _tree():
    return Selector(
        'recovery',
        Sequence(
            'apply_recovery_plan',
            Condition('has_plan', lambda ctx: bool(ctx['plan'])),
            Action('translate_recovery', lambda ctx: _translate(ctx['plan'])),
        ),
        Action('noop', lambda _ctx: [{'action': 'noop'}]),
    )


def evaluate_recovery(supervisor_state: dict) -> list[dict[str, object]]:
    plan = supervisor_state.get('recovery_plan', []) if isinstance(supervisor_state, dict) else []
    return _tree().evaluate({'plan': plan}).actions
