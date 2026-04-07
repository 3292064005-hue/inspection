from __future__ import annotations

from inspection_orchestrator.bt import Action, Condition, Selector, Sequence


def _tree():
    return Selector(
        'startup',
        Sequence(
            'healthy_start',
            Condition('all_required_healthy', lambda ctx: bool(ctx['healthy'])),
            Action('start_auto_cycle', lambda _ctx: [{'action': 'start_auto_cycle'}]),
        ),
        Action('await_health', lambda _ctx: [{'action': 'await_health'}]),
    )


def evaluate_startup(supervisor_state: dict) -> list[dict[str, object]]:
    health = supervisor_state.get('health', {}) if isinstance(supervisor_state, dict) else {}
    return _tree().evaluate({'healthy': bool(health.get('healthy'))}).actions
