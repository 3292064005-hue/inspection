from __future__ import annotations

from inspection_orchestrator.bt import Action, Condition, Selector, Sequence


def _tree():
    return Selector(
        'auto_run',
        Sequence(
            'healthy_resume',
            Condition('health_ok', lambda ctx: bool(ctx['healthy']) and ctx['overall'] == 'OK'),
            Action('resume', lambda _ctx: [{'action': 'resume'}]),
        ),
        Sequence(
            'warn_pause',
            Condition('diagnostics_warn', lambda ctx: ctx['overall'] == 'WARN'),
            Action('pause_warn', lambda _ctx: [{'action': 'pause', 'reason': 'diagnostics_warn'}]),
        ),
        Sequence(
            'error_recovery',
            Condition('diagnostics_error', lambda ctx: ctx['overall'] == 'ERROR'),
            Action('pause_recovery', lambda _ctx: [{'action': 'pause', 'reason': 'diagnostics_error'}, {'action': 'request_recovery'}]),
        ),
        Action('noop', lambda _ctx: [{'action': 'noop'}]),
    )


def evaluate_auto_run(supervisor_state: dict, diagnostics: dict) -> list[dict[str, object]]:
    health = supervisor_state.get('health', {}) if isinstance(supervisor_state, dict) else {}
    overall = str(diagnostics.get('overall_level', 'OK')) if isinstance(diagnostics, dict) else 'OK'
    result = _tree().evaluate({'healthy': bool(health.get('healthy')), 'overall': overall})
    return result.actions
