from __future__ import annotations

from inspection_orchestrator.tree_runtime import OrchestratorPlanResult, OrchestratorTreeRuntime, evaluate_tree_actions, evaluate_tree_plan


def plan_benchmark(supervisor_state: dict, diagnostics: dict, *, runtime: OrchestratorTreeRuntime | None = None) -> OrchestratorPlanResult:
    return evaluate_tree_plan('benchmark', supervisor_state=supervisor_state, diagnostics=diagnostics, runtime=runtime)


def evaluate_benchmark(supervisor_state: dict, diagnostics: dict, *, runtime: OrchestratorTreeRuntime | None = None) -> list[dict[str, object]]:
    return evaluate_tree_actions('benchmark', supervisor_state=supervisor_state, diagnostics=diagnostics, runtime=runtime)
