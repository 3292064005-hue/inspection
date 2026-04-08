from __future__ import annotations
import json
from dataclasses import dataclass
from typing import Any, Callable
from .action_contract import ACTION_CONTRACTS
from .ros_action_bridge import _load_action_type
@dataclass(slots=True)
class NativeActionClientMetrics:
    submitted: int = 0
    cancelled: int = 0
    feedback_updates: int = 0
    goal_rejections: int = 0
    result_failures: int = 0
    def to_dict(self) -> dict[str, int]:
        return {'submitted': int(self.submitted), 'cancelled': int(self.cancelled), 'feedbackUpdates': int(self.feedback_updates), 'goalRejections': int(self.goal_rejections), 'resultFailures': int(self.result_failures)}
def native_action_client_availability() -> dict[str, object]:
    try:
        from rclpy.action import ActionClient  # noqa: F401
    except Exception:
        return {'enabled': False, 'reason': 'rclpy_action_unavailable', 'actions': []}
    actions=[]
    for kind, contract in ACTION_CONTRACTS.items():
        if _load_action_type(contract.ros_type) is not None:
            actions.append({'kind': kind, 'topic': contract.topic, 'type': contract.ros_type})
    return {'enabled': bool(actions), 'reason': '' if actions else 'generated_action_types_unavailable', 'actions': actions}
def _apply_payload_to_goal(kind: str, payload: dict[str, Any], goal: Any) -> None:
    normalized = str(kind or '').strip().lower()
    if normalized == 'start_batch': goal.batch_id = str(payload.get('batchId', '')); goal.recipe_id = str(payload.get('recipeId', ''))
    elif normalized == 'reset_station': goal.reason = str(payload.get('reason', ''))
    elif normalized == 'run_calibration': goal.calibration_profile = str(payload.get('profile', payload.get('profileName', 'default')))
    elif normalized == 'execute_replay': goal.trace_id = str(payload.get('traceId', ''))
    elif normalized == 'export_batch': goal.batch_id = str(payload.get('batchId', ''))
    elif normalized == 'run_benchmark': goal.profile_name = str(payload.get('profileName', 'default'))
    else: goal.recipe_id = str(payload.get('recipeId', '')); goal.validate_only = bool(payload.get('dryRun', False))
class NativeActionClientAdapter:
    def __init__(self, node: Any, *, goal_timeout_sec: float = 1.5) -> None:
        self.node = node; self.goal_timeout_sec = max(0.1, float(goal_timeout_sec)); self.metrics = NativeActionClientMetrics(); self.availability = native_action_client_availability(); self._clients={}; self._updates={}; self._goal_handles={}
        if not self.availability.get('enabled'):
            self._action_client_type = None; return
        try:
            from rclpy.action import ActionClient
        except Exception:
            self._action_client_type = None; self.availability = {'enabled': False, 'reason': 'rclpy_action_unavailable', 'actions': []}; return
        self._action_client_type = ActionClient
    def _client_for(self, kind: str) -> Any | None:
        normalized = str(kind or '').strip().lower(); existing = self._clients.get(normalized)
        if existing is not None: return existing
        contract = ACTION_CONTRACTS.get(normalized)
        if contract is None or self._action_client_type is None: return None
        action_type = _load_action_type(contract.ros_type)
        if action_type is None: return None
        client = self._action_client_type(self.node, action_type, contract.topic); self._clients[normalized] = client; return client
    def submit(self, record: dict[str, Any], *, actor: dict[str, Any], update: Callable[..., None]) -> bool:
        normalized_kind = str(record.get('kind', '')).strip().lower(); job_id = str(record.get('jobId', '')).strip()
        if not normalized_kind or not job_id: return False
        client = self._client_for(normalized_kind)
        if client is None: return False
        try:
            if not client.wait_for_server(timeout_sec=self.goal_timeout_sec): return False
        except Exception:
            return False
        action_type = _load_action_type(ACTION_CONTRACTS[normalized_kind].ros_type)
        if action_type is None: return False
        goal = action_type.Goal(); _apply_payload_to_goal(normalized_kind, dict(record.get('payload', {})), goal); self._updates[job_id] = update
        try:
            future = client.send_goal_async(goal, feedback_callback=lambda msg, _job_id=job_id: self._on_feedback(_job_id, msg)); future.add_done_callback(lambda fut, _job_id=job_id: self._on_goal_response(_job_id, fut))
        except Exception:
            self._updates.pop(job_id, None); return False
        self.metrics.submitted += 1; return True
    def cancel(self, job_id: str, actor: dict[str, Any]) -> bool:
        goal_handle = self._goal_handles.get(str(job_id), None)
        if goal_handle is None: return False
        try:
            future = goal_handle.cancel_goal_async(); future.add_done_callback(lambda _fut, _job_id=str(job_id): self._mark_cancel_requested(_job_id, actor))
        except Exception:
            return False
        self.metrics.cancelled += 1; return True
    def _mark_cancel_requested(self, job_id: str, actor: dict[str, Any]) -> None:
        update = self._updates.get(job_id)
        if callable(update): update(job_id, status='CANCELLING', message='已通过原生 ROS Action 请求取消。', cancelledBy=str(actor.get('username', 'anonymous')))
    def _on_feedback(self, job_id: str, feedback_msg: Any) -> None:
        update = self._updates.get(job_id)
        if not callable(update): return
        feedback = getattr(feedback_msg, 'feedback', feedback_msg); detail_json = str(getattr(feedback, 'detail_json', '') or '{}')
        try: detail = json.loads(detail_json) if detail_json else {}
        except Exception: detail = {'raw': detail_json}
        self.metrics.feedback_updates += 1
        update(job_id, status='RUNNING', progress=max(0, min(100, int(float(getattr(feedback, 'progress', 0.0) or 0.0) * 100.0))), message=str(getattr(feedback, 'phase', 'RUNNING') or 'RUNNING'), feedback={'phase': str(getattr(feedback, 'phase', 'RUNNING') or 'RUNNING'), 'progress': float(getattr(feedback, 'progress', 0.0) or 0.0), 'detail': detail if isinstance(detail, dict) else {'detail': detail}})
    def _on_goal_response(self, job_id: str, future: Any) -> None:
        update = self._updates.get(job_id)
        if not callable(update): return
        try: goal_handle = future.result()
        except Exception as exc:
            self.metrics.goal_rejections += 1; update(job_id, status='FAILED', message=f'native_action_goal_failed:{exc}'); return
        if goal_handle is None or not bool(getattr(goal_handle, 'accepted', False)):
            self.metrics.goal_rejections += 1; update(job_id, status='FAILED', message='native_action_goal_rejected'); return
        self._goal_handles[job_id] = goal_handle; update(job_id, status='RUNNING', message='任务已由原生 ROS Action 接收。')
        try:
            result_future = goal_handle.get_result_async(); result_future.add_done_callback(lambda fut, _job_id=job_id: self._on_result(_job_id, fut))
        except Exception as exc:
            self.metrics.result_failures += 1; update(job_id, status='FAILED', message=f'native_action_result_wait_failed:{exc}')
    def _on_result(self, job_id: str, future: Any) -> None:
        update = self._updates.pop(job_id, None); self._goal_handles.pop(job_id, None)
        if not callable(update): return
        try: wrapper = future.result(); result = getattr(wrapper, 'result', wrapper); status_code = getattr(wrapper, 'status', None)
        except Exception as exc:
            self.metrics.result_failures += 1; update(job_id, status='FAILED', message=f'native_action_result_failed:{exc}'); return
        message = str(getattr(result, 'message', '') or ''); accepted = bool(getattr(result, 'accepted', False)); export_url = str(getattr(result, 'export_url', '') or '')
        status = 'CANCELLED' if status_code == 5 or 'cancel' in message.lower() else ('COMPLETED' if accepted else 'FAILED')
        payload={'accepted': accepted, 'message': message}
        if export_url: payload['exportUrl']=export_url
        update(job_id, status=status, progress=100, message=message or status, result=payload)
    def snapshot(self) -> dict[str, Any]:
        return {**self.availability, 'metrics': self.metrics.to_dict()}
