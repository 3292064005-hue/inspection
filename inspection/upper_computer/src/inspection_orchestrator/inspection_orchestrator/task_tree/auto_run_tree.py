from __future__ import annotations

from inspection_orchestrator.tree_runtime import OrchestratorPlanResult, OrchestratorTreeRuntime, evaluate_tree_actions, evaluate_tree_plan


def plan_auto_run(supervisor_state: dict, diagnostics: dict, *, runtime: OrchestratorTreeRuntime | None = None) -> OrchestratorPlanResult:
    return evaluate_tree_plan('auto_run', supervisor_state=supervisor_state, diagnostics=diagnostics, runtime=runtime)


def evaluate_auto_run(supervisor_state: dict, diagnostics: dict, *, runtime: OrchestratorTreeRuntime | None = None) -> list[dict[str, object]]:
    return evaluate_tree_actions('auto_run', supervisor_state=supervisor_state, diagnostics=diagnostics, runtime=runtime)
