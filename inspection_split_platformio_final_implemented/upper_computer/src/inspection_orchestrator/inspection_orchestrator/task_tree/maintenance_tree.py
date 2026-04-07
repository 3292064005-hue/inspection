from __future__ import annotations

from inspection_orchestrator.bt import Action, Condition, Selector, Sequence


def _tree():
    return Selector(
        'maintenance',
        Sequence(
            'enter_manual',
            Condition('mode_maintenance', lambda ctx: ctx['mode'] == 'MAINTENANCE'),
            Action('enter_manual', lambda _ctx: [{'action': 'enter_manual'}]),
        ),
        Action('noop', lambda _ctx: [{'action': 'noop'}]),
    )


def evaluate_maintenance(supervisor_state: dict) -> list[dict[str, object]]:
    mode = str(supervisor_state.get('mode', {}).get('current_mode', 'STOPPED')) if isinstance(supervisor_state, dict) else 'STOPPED'
    return _tree().evaluate({'mode': mode}).actions
