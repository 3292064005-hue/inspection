from __future__ import annotations

from inspection_orchestrator.tree_runtime import OrchestratorPlanResult, OrchestratorTreeRuntime, evaluate_tree_actions, evaluate_tree_plan


def plan_maintenance(supervisor_state: dict, *, runtime: OrchestratorTreeRuntime | None = None) -> OrchestratorPlanResult:
    return evaluate_tree_plan('maintenance', supervisor_state=supervisor_state, diagnostics={}, runtime=runtime)


def evaluate_maintenance(supervisor_state: dict, *, runtime: OrchestratorTreeRuntime | None = None) -> list[dict[str, object]]:
    return evaluate_tree_actions('maintenance', supervisor_state=supervisor_state, diagnostics={}, runtime=runtime)
