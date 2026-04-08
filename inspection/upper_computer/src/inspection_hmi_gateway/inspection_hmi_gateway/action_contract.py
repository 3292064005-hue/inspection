from __future__ import annotations

"""Action contract definitions and execution-governance helpers.

This module is the single source of truth for:
- transport metadata exposed to HTTP/ROS callers,
- payload validation,
- capability grading exposed in the action catalog, and
- submission policy checks enforced before action execution.
"""

from dataclasses import dataclass
import os
from typing import Any


EXECUTOR_SUBMIT_TOPIC = '/inspection/action_executor/submit'
EXECUTOR_CANCEL_TOPIC = '/inspection/action_executor/cancel'
EXECUTOR_EVENT_TOPIC = '/inspection/action_executor/events'
EXPERIMENTAL_ACTIONS_ENV = 'INSPECTION_EXPERIMENTAL_ACTIONS_ENABLED'


class ActionPolicyError(PermissionError):
    """Raised when an action is visible in the catalog but cannot be executed.

    Args:
        kind: Normalized action kind.
        reason: Machine-readable rejection reason.
        message: Human-readable rejection message.

    Returns:
        None.

    Raises:
        PermissionError: Base class used by HTTP/API and ROS entry points.

    Boundary behavior:
        The original reason is preserved in ``reason`` so routers and action
        bridges can map the rejection to transport-specific error payloads.
    """

    def __init__(self, kind: str, reason: str, message: str) -> None:
        self.kind = str(kind or '').strip().lower()
        self.reason = str(reason or 'action_execution_blocked').strip() or 'action_execution_blocked'
        self.user_message = str(message or '动作当前不可执行。').strip() or '动作当前不可执行。'
        super().__init__(self.user_message)

    def to_payload(self) -> dict[str, str]:
        return {'code': self.reason, 'kind': self.kind, 'message': self.user_message}


class ActionDispatchError(RuntimeError):
    """Raised when a job record is created but execution transport cannot accept it.

    Args:
        kind: Normalized action kind.
        reason: Machine-readable failure reason.
        message: Human-readable failure message.
        job_id: Persisted job identifier associated with the failed submission.
        transport: Selected transport name when known.

    Boundary behavior:
        Routers map this exception to a structured 503 response instead of
        leaking a generic 500 while the failed job remains visible for audit.
    """

    def __init__(self, kind: str, reason: str, message: str, *, job_id: str = '', transport: str = '') -> None:
        self.kind = str(kind or '').strip().lower()
        self.reason = str(reason or 'action_transport_unavailable').strip() or 'action_transport_unavailable'
        self.user_message = str(message or '动作提交失败，执行链路当前不可用。').strip() or '动作提交失败，执行链路当前不可用。'
        self.job_id = str(job_id or '').strip()
        self.transport = str(transport or '').strip()
        super().__init__(self.user_message)

    def to_payload(self) -> dict[str, str]:
        return {
            'code': self.reason,
            'kind': self.kind,
            'message': self.user_message,
            'jobId': self.job_id,
            'transport': self.transport,
        }


@dataclass(frozen=True, slots=True)
class ActionCapability:
    """Describes the delivery maturity and execution policy of an action."""

    availability: str
    visibility: str = 'visible'
    execution_policy: str = 'allowed'
    runtime_truth: str = 'real'
    summary: str = ''
    blocked_reason: str = ''
    experimental_env: str = EXPERIMENTAL_ACTIONS_ENV

    def submit_state(self) -> tuple[bool, str]:
        """Resolve whether the action may be submitted in the current process.

        Returns:
            ``(allowed, reason)`` where ``reason`` is empty on success.

        Raises:
            No exception is raised. Invalid policy strings fall back to blocked.

        Boundary behavior:
            ``experimental`` actions become executable only when the configured
            environment variable is explicitly enabled.
        """
        policy = str(self.execution_policy or 'blocked').strip().lower()
        if policy == 'allowed':
            return True, ''
        if policy == 'experimental':
            enabled = str(os.environ.get(self.experimental_env, '')).strip().lower() in {'1', 'true', 'yes', 'on'}
            if enabled:
                return True, ''
            return False, self.blocked_reason or f'enable_{self.experimental_env.lower()}'
        return False, self.blocked_reason or 'action_execution_blocked'

    def to_dict(self) -> dict[str, object]:
        allowed, reason = self.submit_state()
        return {
            'availability': self.availability,
            'visibility': self.visibility,
            'executionPolicy': self.execution_policy,
            'runtimeTruth': self.runtime_truth,
            'summary': self.summary,
            'submitEnabled': allowed,
            'submitReason': reason,
            'experimentalEnv': self.experimental_env if self.execution_policy == 'experimental' else '',
        }


@dataclass(frozen=True, slots=True)
class ActionContract:
    """Static action metadata exposed to API, ROS bridges, and executors."""

    kind: str
    ros_type: str
    topic: str
    required_payload: tuple[str, ...] = ()
    capability: ActionCapability = ActionCapability(availability='production_ready')

    def to_dict(self) -> dict[str, object]:
        return {
            'kind': self.kind,
            'type': self.ros_type,
            'topic': self.topic,
            'requiredPayload': list(self.required_payload),
            'capability': self.capability.to_dict(),
        }


ACTION_CONTRACTS: dict[str, ActionContract] = {
    'start_batch': ActionContract(
        'start_batch',
        'StartBatch',
        '/inspection/actions/start_batch',
        ('recipeId',),
        ActionCapability(availability='production_ready', runtime_truth='real', summary='正式批次启动链路。'),
    ),
    'reset_station': ActionContract(
        'reset_station',
        'ResetStation',
        '/inspection/actions/reset_station',
        capability=ActionCapability(availability='production_ready', runtime_truth='real', summary='正式复位与恢复链路。'),
    ),
    'run_calibration': ActionContract(
        'run_calibration',
        'RunCalibration',
        '/inspection/actions/run_calibration',
        capability=ActionCapability(
            availability='disabled',
            visibility='hidden',
            execution_policy='blocked',
            runtime_truth='blocked',
            summary='标定闭环尚未落地，当前仅保留目录位。',
            blocked_reason='calibration_workflow_not_available',
        ),
    ),
    'execute_replay': ActionContract(
        'execute_replay',
        'ExecuteReplay',
        '/inspection/actions/execute_replay',
        ('traceId',),
        ActionCapability(availability='production_ready', runtime_truth='real', summary='回放与对比分析链路。'),
    ),
    'export_batch': ActionContract(
        'export_batch',
        'ExportBatch',
        '/inspection/actions/export_batch',
        ('batchId',),
        ActionCapability(availability='production_ready', runtime_truth='real', summary='批次导出链路。'),
    ),
    'run_benchmark': ActionContract(
        'run_benchmark',
        'RunBenchmark',
        '/inspection/actions/run_benchmark',
        capability=ActionCapability(
            availability='synthetic',
            visibility='experimental',
            execution_policy='experimental',
            runtime_truth='synthetic',
            summary='仅提供合成基准样本，不代表真实工艺闭环。',
            blocked_reason='benchmark_requires_experimental_actions',
        ),
    ),
    'switch_recipe_with_validation': ActionContract(
        'switch_recipe_with_validation',
        'SwitchRecipeWithValidation',
        '/inspection/actions/switch_recipe',
        ('recipeId',),
        ActionCapability(availability='production_ready', runtime_truth='real', summary='配方校验与激活链路。'),
    ),
    'stop_station': ActionContract(
        'stop_station',
        'StopStation',
        '/inspection/actions/stop_station',
        capability=ActionCapability(availability='production_ready', runtime_truth='real', summary='正式停线控制链路。'),
    ),
    'set_maintenance_mode': ActionContract(
        'set_maintenance_mode',
        'SetMaintenanceMode',
        '/inspection/actions/set_maintenance_mode',
        ('enabled',),
        ActionCapability(availability='production_ready', runtime_truth='real', summary='维护模式切换链路。'),
    ),
    'create_batch': ActionContract(
        'create_batch',
        'CreateBatch',
        '/inspection/actions/create_batch',
        capability=ActionCapability(availability='production_ready', runtime_truth='real', summary='新批次号申请链路。'),
    ),
    'diagnostic_capture_frame': ActionContract(
        'diagnostic_capture_frame',
        'DiagnosticCaptureFrame',
        '/inspection/actions/diagnostics/capture_frame',
        capability=ActionCapability(availability='production_ready', runtime_truth='real', summary='维护态抓帧诊断动作，复用正式诊断服务。'),
    ),
    'diagnostic_test_lighting': ActionContract(
        'diagnostic_test_lighting',
        'DiagnosticTestLighting',
        '/inspection/actions/diagnostics/test_lighting',
        capability=ActionCapability(availability='production_ready', runtime_truth='real', summary='维护态补光测试动作，复用正式诊断服务。'),
    ),
    'diagnostic_test_sort_actuator': ActionContract(
        'diagnostic_test_sort_actuator',
        'DiagnosticTestSortActuator',
        '/inspection/actions/diagnostics/test_sort_actuator',
        capability=ActionCapability(availability='production_ready', runtime_truth='real', summary='维护态分拣执行器测试动作，复用正式诊断服务。'),
    ),
}


def action_contract(kind: str) -> ActionContract:
    """Return the normalized action contract for ``kind``.

    Args:
        kind: Caller-provided action kind.

    Returns:
        The matching ``ActionContract``.

    Raises:
        KeyError: When ``kind`` does not exist in the action registry.

    Boundary behavior:
        The lookup is case-insensitive and ignores leading/trailing whitespace.
    """
    normalized = str(kind or '').strip().lower()
    return ACTION_CONTRACTS[normalized]



def action_catalog(*, include_non_production: bool = True) -> list[dict[str, object]]:
    """Return the externally exposed action catalog with capability metadata.

    Args:
        include_non_production: When ``False``, only production-ready actions
            intended for public/operator discovery are included. Disabled and
            experimental capabilities stay executable only via explicit internal
            knowledge of their endpoint and policy gate.

    Returns:
        Ordered action catalog payloads.

    Boundary behavior:
        The internal registry remains authoritative even when the public catalog
        intentionally hides non-production actions from default discovery.
    """
    items: list[dict[str, object]] = []
    for contract in ACTION_CONTRACTS.values():
        capability = contract.capability
        if not include_non_production and (capability.availability != 'production_ready' or capability.visibility != 'visible'):
            continue
        items.append(contract.to_dict())
    return items



def action_submit_state(kind: str) -> tuple[bool, str]:
    """Resolve whether the current process may submit ``kind``.

    Args:
        kind: Action kind to evaluate.

    Returns:
        ``(allowed, reason)``.

    Raises:
        KeyError: When the action kind is unknown.

    Boundary behavior:
        Dynamic policy is resolved against the current environment variables.
    """
    return action_contract(kind).capability.submit_state()



def ensure_action_submit_allowed(kind: str) -> ActionContract:
    """Validate that an action may be submitted before any job record is created.

    Args:
        kind: Action kind to evaluate.

    Returns:
        The normalized ``ActionContract`` for downstream callers.

    Raises:
        ActionPolicyError: When the action is catalogued but execution is blocked.
        KeyError: When the action kind is unknown.

    Boundary behavior:
        The returned contract is safe to reuse for audit records and job payloads.
    """
    contract = action_contract(kind)
    allowed, reason = contract.capability.submit_state()
    if allowed:
        return contract
    raise ActionPolicyError(contract.kind, reason, contract.capability.summary or '动作当前不可执行。')



def validate_action_payload(kind: str, payload: dict[str, Any]) -> str:
    normalized = str(kind or '').strip().lower()
    contract = ACTION_CONTRACTS.get(normalized)
    if contract is None:
        return f'unsupported_action_kind:{normalized}'
    for key in contract.required_payload:
        if not str(payload.get(key, '')).strip():
            return f'{key} is required'
    return ''



def payload_from_goal(kind: str, request: Any) -> dict[str, Any]:
    normalized = str(kind or '').strip().lower()
    if normalized == 'start_batch':
        return {'batchId': str(getattr(request, 'batch_id', '')), 'recipeId': str(getattr(request, 'recipe_id', ''))}
    if normalized == 'reset_station':
        return {'reason': str(getattr(request, 'reason', '')), 'resumeAfter': False}
    if normalized == 'run_calibration':
        return {'profile': str(getattr(request, 'calibration_profile', 'default'))}
    if normalized == 'execute_replay':
        return {'traceId': str(getattr(request, 'trace_id', ''))}
    if normalized == 'export_batch':
        return {'batchId': str(getattr(request, 'batch_id', ''))}
    if normalized == 'run_benchmark':
        return {'profileName': str(getattr(request, 'profile_name', 'default'))}
    return {'recipeId': str(getattr(request, 'recipe_id', '')), 'dryRun': bool(getattr(request, 'validate_only', False))}
