from __future__ import annotations

"""Declarative action-workflow helpers.

The workflow layer keeps multi-step action orchestration out of individual
handlers so maintenance, control, and recovery flows can share the same guarded
execution semantics.
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    """One declarative step in an action workflow."""

    progress: int
    message: str
    perform: Callable[[], Any] | None = None
    sleep_sec: float = 0.0


class ActionWorkflowRunner:
    """Execute declarative action workflows with shared progress handling.

    Args:
        runtime: Shared action runtime that provides ``_step``.
        cancel_flag: Cooperative cancellation flag provided by the execution
            runtime.
        update: Job-state update callback.

    Returns:
        None. Results are produced by the supplied step callbacks.

    Raises:
        Any exception raised by a step callback is propagated to the caller.

    Boundary behavior:
        Progress updates are always emitted before a step callback runs, which
        keeps job-state history deterministic across real and rollback runtimes.
    """

    def __init__(self, runtime: Any, cancel_flag: Any, update: Callable[..., None]) -> None:
        self._runtime = runtime
        self._cancel_flag = cancel_flag
        self._update = update

    def run(self, job_id: str, *steps: WorkflowStep) -> None:
        for step in steps:
            self._runtime._step(
                job_id,
                self._cancel_flag,
                self._update,
                progress=int(step.progress),
                message=str(step.message),
                sleep_sec=float(step.sleep_sec),
            )
            if step.perform is not None:
                step.perform()


def start_batch_workflow(*, app: Any, batch_id: str, recipe_id: str, result_sink: dict[str, Any]) -> tuple[WorkflowStep, ...]:
    """Build the canonical batch-start workflow."""
    return (
        WorkflowStep(progress=15, message='准备批次上下文。'),
        WorkflowStep(progress=55, message='下发启动请求。', perform=lambda: result_sink.update(_start_result=app.call_start(recipe_id=recipe_id, batch_id=batch_id))),
        WorkflowStep(progress=90, message='批次已启动。'),
    )


def benchmark_workflow(*, app: Any) -> tuple[WorkflowStep, ...]:
    """Build the explicitly synthetic benchmark workflow."""
    return (
        WorkflowStep(progress=10, message='下发暂停指令。', perform=lambda: app.publish_control('pause')),
        WorkflowStep(progress=20, message='准备基准测试环境。', sleep_sec=0.01),
        WorkflowStep(progress=35, message='恢复采样通道。', perform=lambda: app.publish_control('resume')),
        WorkflowStep(progress=70, message='执行基准采样。', sleep_sec=0.02),
    )


def reset_station_workflow(*, app: Any, resume_after: bool, result_sink: dict[str, Any]) -> tuple[WorkflowStep, ...]:
    """Build the station-reset workflow with optional resume."""
    steps = [
        WorkflowStep(progress=20, message='下发暂停指令。', perform=lambda: app.publish_control('pause')),
        WorkflowStep(progress=50, message='执行故障复位。', perform=lambda: result_sink.update(_reset_result=app.reset_fault()), sleep_sec=0.01),
    ]
    if resume_after:
        steps.append(WorkflowStep(progress=80, message='恢复自动运行。', perform=lambda: app.publish_control('resume')))
    return tuple(steps)


def stop_station_workflow(*, app: Any) -> tuple[WorkflowStep, ...]:
    """Build the canonical stop-station workflow."""
    return (
        WorkflowStep(progress=25, message='下发停线指令。', perform=lambda: app.publish_control('stop')),
        WorkflowStep(progress=90, message='停线指令已提交。'),
    )


def maintenance_mode_workflow(*, app: Any, enabled: bool, actor: str, result_sink: dict[str, Any]) -> tuple[WorkflowStep, ...]:
    """Build the maintenance-mode transition workflow."""
    return (
        WorkflowStep(progress=30, message='提交维护模式切换请求。', perform=lambda: result_sink.update(snapshot=app.request_maintenance_mode(enabled, actor=actor))),
        WorkflowStep(progress=90, message='维护模式请求已提交。'),
    )


def diagnostic_action_workflow(*, app: Any, diagnostic_action: str, result_sink: dict[str, Any]) -> tuple[WorkflowStep, ...]:
    """Build the maintenance-only diagnostic workflow."""
    return (
        WorkflowStep(progress=20, message='校验维护态。'),
        WorkflowStep(progress=60, message='执行诊断动作。', perform=lambda: result_sink.update(result=app.run_diagnostic_action(diagnostic_action))),
        WorkflowStep(progress=90, message='诊断动作执行完成。'),
    )


def switch_recipe_workflow(*, app: Any, recipe_id: str, dry_run: bool, actor: str, result_sink: dict[str, Any]) -> tuple[WorkflowStep, ...]:
    """Build the recipe switch workflow with explicit validation evidence.

    Args:
        app: Gateway application service exposing recipe persistence and station
            command planes.
        recipe_id: Target recipe identifier.
        dry_run: When true, collect prospective validation evidence without
            mutating the active recipe snapshot.
        actor: Authenticated operator name used for activation receipts.
        result_sink: Mutable result collector shared with the action handler.

    Returns:
        Tuple of declarative workflow steps consumed by
        :class:`ActionWorkflowRunner`.

    Raises:
        FileNotFoundError: The requested recipe snapshot does not exist.
        RuntimeError: Activation or preflight validation fails.

    Boundary behavior:
        Dry-run mode validates a staged activation candidate without mutating
        activation receipts. Non-dry-run mode validates the same staged
        candidate before committing the target recipe, so pre-commit failure
        leaves the previous active/default recipe untouched.
    """

    def _load_recipe() -> None:
        recipe = app.recipe_store.load_by_id(recipe_id)
        if not recipe:
            raise FileNotFoundError(f'recipe_not_found:{recipe_id}')
        result_sink['recipe'] = recipe
        result_sink['validation'] = {
            'recipeLoaded': True,
            'recipeSnapshotValid': True,
            'startContractValid': False,
            'validationCompleted': False,
            'validationMode': 'pre_activation_preview' if dry_run else 'pre_activation_commit',
            'message': '',
            'recipeId': recipe_id,
            'recipeVersion': str(recipe.get('version', '1.0.0')),
            'configGeneration': str(app.recipe_store._config_generation(recipe)),
            'activeRecipeIdBefore': str(getattr(app.state, 'active_recipe_id', '') or ''),
            'defaultRecipeIdBefore': str((app.recipe_store.current_default() or {}).get('recipe_id', '')),
            'activationStateBefore': str((app.recipe_store.current_activation() or {}).get('activationState', '')),
            'activationRequired': not dry_run,
            'stateMutated': False,
            'valid': False,
            'preflight': {
                'executed': False,
                'valid': False,
                'mode': 'pre_activation_preview' if dry_run else 'pre_activation_commit',
                'batchId': 'VALIDATION-PREVIEW',
                'message': '',
            },
        }

    def _evaluate_or_activate() -> None:
        validation = result_sink.setdefault('validation', {})
        candidate = app.recipe_store.validate_activation_candidate(
            recipe_id=recipe_id,
            batch_id='VALIDATION-PREVIEW',
            operator=actor,
        )
        candidate_preflight = dict(candidate.get('preflight', {}) or {})
        validation['recipeSnapshotValid'] = True
        validation['startContractValid'] = bool(candidate_preflight.get('valid', False))
        validation['validationCompleted'] = True
        validation['valid'] = bool(candidate_preflight.get('valid', False))
        validation['stateMutated'] = False
        validation['message'] = str(candidate_preflight.get('message', '配方候选已通过无副作用切换与启动前契约校验。'))
        validation['preflight'] = {
            'executed': True,
            'valid': bool(candidate_preflight.get('valid', False)),
            'mode': validation.get('validationMode', 'pre_activation'),
            'batchId': str(candidate.get('batchId', 'VALIDATION-PREVIEW')),
            'message': str(candidate_preflight.get('message', 'staged activation candidate passed without mutating active recipe.')),
            'activationState': str((candidate.get('activation', {}) or {}).get('activationState', 'PENDING_START')),
            'configGeneration': str(candidate_preflight.get('configGeneration', candidate.get('configGeneration', ''))),
        }
        validation['stagedActivationState'] = str((candidate.get('activation', {}) or {}).get('activationState', 'PENDING_START'))
        if dry_run:
            validation['activationRequired'] = True
            result_sink['activation'] = {
                'recipeId': recipe_id,
                'dryRun': True,
                'activationState': 'DRY_RUN',
                'stateMutated': False,
            }
            return
        activation = app.activate_recipe(recipe_id, operator=actor)
        validation['activationRequired'] = False
        validation['stateMutated'] = True
        validation['activationStateAfter'] = str((activation or {}).get('activationState', ''))
        validation['defaultRecipeIdAfter'] = recipe_id
        result_sink['activation'] = activation

    return (
        WorkflowStep(progress=20, message='装载目标配方并生成校验快照。', perform=_load_recipe),
        WorkflowStep(progress=60, message='执行无副作用配方切换预检。' if dry_run else '预检通过后提交配方激活。', perform=_evaluate_or_activate),
        WorkflowStep(progress=90, message='写入配方切换结果。'),
    )
