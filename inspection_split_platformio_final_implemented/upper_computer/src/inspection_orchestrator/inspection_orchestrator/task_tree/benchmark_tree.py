from __future__ import annotations

from inspection_orchestrator.bt import Action, Condition, Selector, Sequence


def _tree():
    return Selector(
        'benchmark',
        Sequence(
            'benchmark_run',
            Condition('healthy_and_ok', lambda ctx: bool(ctx['healthy']) and ctx['level'] == 'OK'),
            Action('resume', lambda _ctx: [{'action': 'resume', 'reason': 'benchmark_run'}]),
        ),
        Sequence(
            'benchmark_unhealthy',
            Condition('unhealthy', lambda ctx: not bool(ctx['healthy'])),
            Action('pause_unhealthy', lambda _ctx: [{'action': 'pause', 'reason': 'benchmark_requires_healthy_stack'}]),
        ),
        Action('pause_degraded', lambda _ctx: [{'action': 'pause', 'reason': 'benchmark_diagnostics_not_ok'}]),
    )


def evaluate_benchmark(supervisor_state: dict, diagnostics: dict) -> list[dict[str, object]]:
    health = supervisor_state.get('health', {}) if isinstance(supervisor_state, dict) else {}
    level = str(diagnostics.get('overall_level', 'OK')) if isinstance(diagnostics, dict) else 'OK'
    return _tree().evaluate({'healthy': bool(health.get('healthy')), 'level': level}).actions
