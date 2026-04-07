from __future__ import annotations

from dataclasses import dataclass
from typing import Any



EXECUTOR_SUBMIT_TOPIC = '/inspection/action_executor/submit'
EXECUTOR_CANCEL_TOPIC = '/inspection/action_executor/cancel'
EXECUTOR_EVENT_TOPIC = '/inspection/action_executor/events'

@dataclass(frozen=True, slots=True)
class ActionContract:
    kind: str
    ros_type: str
    topic: str
    required_payload: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            'kind': self.kind,
            'type': self.ros_type,
            'topic': self.topic,
            'requiredPayload': list(self.required_payload),
        }


ACTION_CONTRACTS: dict[str, ActionContract] = {
    'start_batch': ActionContract('start_batch', 'StartBatch', '/inspection/actions/start_batch', ('recipeId',)),
    'reset_station': ActionContract('reset_station', 'ResetStation', '/inspection/actions/reset_station'),
    'run_calibration': ActionContract('run_calibration', 'RunCalibration', '/inspection/actions/run_calibration'),
    'execute_replay': ActionContract('execute_replay', 'ExecuteReplay', '/inspection/actions/execute_replay', ('traceId',)),
    'export_batch': ActionContract('export_batch', 'ExportBatch', '/inspection/actions/export_batch', ('batchId',)),
    'run_benchmark': ActionContract('run_benchmark', 'RunBenchmark', '/inspection/actions/run_benchmark'),
    'switch_recipe_with_validation': ActionContract('switch_recipe_with_validation', 'SwitchRecipeWithValidation', '/inspection/actions/switch_recipe', ('recipeId',)),
}


def action_contract(kind: str) -> ActionContract:
    normalized = str(kind or '').strip().lower()
    return ACTION_CONTRACTS[normalized]


def action_catalog() -> list[dict[str, object]]:
    return [contract.to_dict() for contract in ACTION_CONTRACTS.values()]


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
