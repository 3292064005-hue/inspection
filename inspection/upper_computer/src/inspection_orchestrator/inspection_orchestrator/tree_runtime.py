from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inspection_utils.paths import resolve_resource_path

from .bt import BTResult, build_node_from_spec, context_get, load_tree_catalog, register_action_builder

_DEFAULT_TREE_CONFIG_PATH = 'config/system/orchestrator_trees.yaml'
_REQUIRED_TREES = {'startup', 'auto_run', 'benchmark', 'maintenance', 'recovery'}


def _translate_recovery_plan(context: dict[str, object]) -> list[dict[str, object]]:
    plan = context.get('plan', [])
    translated: list[dict[str, object]] = []
    if not isinstance(plan, list):
        return [{'action': 'noop', 'reason': 'recovery_plan_invalid'}]
    for step in plan:
        if not isinstance(step, dict):
            continue
        action = str(step.get('action', 'noop'))
        if action == 'pause_auto':
            translated.append({'action': 'pause', 'reason': 'pause_auto', 'source_action': action})
        elif action == 'request_reset_if_faulted':
            translated.append({'action': 'reset_fault', 'reason': 'request_reset_if_faulted', 'source_action': action})
    return translated or [{'action': 'noop', 'reason': 'recovery_plan_empty'}]


register_action_builder('translate_recovery_plan', _translate_recovery_plan)


@dataclass(slots=True)
class OrchestratorPlanResult:
    tree: str
    status: str
    actions: list[dict[str, object]]
    trace: list[str]
    duration_ms: int
    context: dict[str, object]


class OrchestratorTreeRuntime:
    """Load and evaluate declarative orchestration trees from config assets."""

    def __init__(self, config_path: str | None = None) -> None:
        self.requested_config_path = str(config_path or _DEFAULT_TREE_CONFIG_PATH)
        self.config_path = resolve_resource_path(self.requested_config_path, package_name='inspection_bringup', start=__file__)
        self._payload = load_tree_catalog(self.config_path)
        self.catalog_version = int(self._payload.get('version', 1) or 1)
        self.root_timeout_ms = max(1, int(self._payload.get('root_timeout_ms', 50) or 50))
        self._tree_specs = self._payload.get('trees', {})
        missing = sorted(_REQUIRED_TREES.difference(self._tree_specs))
        if missing:
            raise ValueError(f'Orchestrator tree catalog is missing required trees: {", ".join(missing)}')
        self._compiled = {name: build_node_from_spec(spec) for name, spec in self._tree_specs.items()}

    def evaluate(self, tree_name: str, context: dict[str, object]) -> OrchestratorPlanResult:
        tree_key = str(tree_name or '').strip()
        if tree_key not in self._compiled:
            raise KeyError(f'Unknown orchestrator tree: {tree_key}')
        node = self._compiled[tree_key]
        tree_context = dict(context)
        if '__deadline_monotonic__' not in tree_context:
            import time

            tree_context['__deadline_monotonic__'] = time.perf_counter() + (self.root_timeout_ms / 1000.0)
        result: BTResult = node.evaluate(tree_context)
        return OrchestratorPlanResult(
            tree=tree_key,
            status=result.status,
            actions=[dict(item) for item in result.actions],
            trace=list(result.trace),
            duration_ms=result.duration_ms,
            context=tree_context,
        )


_DEFAULT_RUNTIME: OrchestratorTreeRuntime | None = None


def default_tree_runtime() -> OrchestratorTreeRuntime:
    global _DEFAULT_RUNTIME
    if _DEFAULT_RUNTIME is None:
        _DEFAULT_RUNTIME = OrchestratorTreeRuntime()
    return _DEFAULT_RUNTIME


def detect_cancel_requested(supervisor_state: dict[str, Any], diagnostics: dict[str, Any]) -> bool:
    supervisor_candidates = [
        context_get(supervisor_state, 'control.cancel_requested', False),
        context_get(supervisor_state, 'cancel_requested', False),
        context_get(supervisor_state, 'mode.cancel_requested', False),
    ]
    diagnostics_candidates = [
        context_get(diagnostics, 'control.cancel_requested', False),
        context_get(diagnostics, 'cancel_requested', False),
    ]
    return any(bool(item) for item in [*supervisor_candidates, *diagnostics_candidates])


def build_tree_context(tree_name: str, supervisor_state: dict[str, Any] | None, diagnostics: dict[str, Any] | None = None) -> dict[str, object]:
    supervisor = dict(supervisor_state or {})
    diag = dict(diagnostics or {})
    health = supervisor.get('health', {}) if isinstance(supervisor.get('health', {}), dict) else {}
    current_mode = str(context_get(supervisor, 'mode.current_mode', supervisor.get('mode', 'STOPPED')))
    plan = supervisor.get('recovery_plan', []) if isinstance(supervisor.get('recovery_plan', []), list) else []
    overall = str(diag.get('overall_level', 'OK')).upper()
    context: dict[str, object] = {
        'tree': str(tree_name),
        'supervisor': supervisor,
        'diagnostics': diag,
        'healthy': bool(health.get('healthy')),
        'overall': overall,
        'level': overall,
        'mode': current_mode,
        'plan': [dict(item) if isinstance(item, dict) else item for item in plan],
        'control': {
            'cancel_requested': detect_cancel_requested(supervisor, diag),
        },
    }
    return context


def evaluate_tree_plan(
    tree_name: str,
    *,
    supervisor_state: dict[str, Any] | None,
    diagnostics: dict[str, Any] | None = None,
    runtime: OrchestratorTreeRuntime | None = None,
) -> OrchestratorPlanResult:
    tree_runtime = runtime or default_tree_runtime()
    context = build_tree_context(tree_name, supervisor_state, diagnostics)
    return tree_runtime.evaluate(tree_name, context)


def evaluate_tree_actions(
    tree_name: str,
    *,
    supervisor_state: dict[str, Any] | None,
    diagnostics: dict[str, Any] | None = None,
    runtime: OrchestratorTreeRuntime | None = None,
) -> list[dict[str, object]]:
    return evaluate_tree_plan(tree_name, supervisor_state=supervisor_state, diagnostics=diagnostics, runtime=runtime).actions
