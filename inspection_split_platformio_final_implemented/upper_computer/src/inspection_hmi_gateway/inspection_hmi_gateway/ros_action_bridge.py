from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Callable

from .action_contract import ACTION_CONTRACTS, payload_from_goal, validate_action_payload


ACTION_NAMES = {kind: (contract.ros_type, contract.topic) for kind, contract in ACTION_CONTRACTS.items()}


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _load_action_type(class_name: str) -> Any | None:
    try:
        module = __import__('inspection_interfaces.action', fromlist=[class_name])
        return getattr(module, class_name)
    except Exception:
        return None


def native_action_availability() -> dict[str, object]:
    try:
        from rclpy.action import ActionServer  # noqa: F401
        from rclpy.action import CancelResponse, GoalResponse  # noqa: F401
    except Exception:
        return {'enabled': False, 'reason': 'rclpy_action_unavailable', 'actions': []}
    actions = []
    for kind, contract in ACTION_CONTRACTS.items():
        if _load_action_type(contract.ros_type) is not None:
            actions.append({'kind': kind, 'topic': contract.topic, 'type': contract.ros_type})
    return {'enabled': bool(actions), 'reason': '' if actions else 'generated_action_types_unavailable', 'actions': actions}


@dataclass(slots=True)
class ActionProvider:
    submit: Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]]
    get_job: Callable[[str], dict[str, Any] | None]
    cancel: Callable[[str, dict[str, Any]], dict[str, Any]]


class RosActionBridge:
    def __init__(self, node: Any, *, poll_interval_sec: float = 0.2, job_timeout_sec: float = 30.0, enable_servers: bool = True) -> None:
        self.node = node
        self.poll_interval_sec = max(0.05, float(poll_interval_sec))
        self.job_timeout_sec = max(0.5, float(job_timeout_sec))
        self.provider: ActionProvider | None = None
        self.servers: list[Any] = []
        self.enable_servers = bool(enable_servers)
        self.availability = native_action_availability()
        if not self.availability.get('enabled'):
            return
        if not self.enable_servers:
            self.availability = {**self.availability, 'serverMode': 'disabled'}
            return
        try:
            from rclpy.action import ActionServer, CancelResponse, GoalResponse
        except Exception:
            self.availability = {'enabled': False, 'reason': 'rclpy_action_unavailable', 'actions': []}
            return
        self._goal_response = GoalResponse
        self._cancel_response = CancelResponse
        for item in self.availability.get('actions', []):
            kind = str(item['kind'])
            topic = str(item['topic'])
            action_type = _load_action_type(str(item['type']))
            if action_type is None:
                continue
            server = ActionServer(
                self.node,
                action_type,
                topic,
                execute_callback=self._make_execute_callback(kind, action_type),
                goal_callback=self._goal_callback,
                cancel_callback=self._cancel_callback,
            )
            self.servers.append(server)

    def register_provider(self, provider: ActionProvider) -> None:
        self.provider = provider

    def destroy(self) -> None:
        for server in list(self.servers):
            try:
                destroy = getattr(server, 'destroy', None)
                if callable(destroy):
                    destroy()
            except Exception:
                pass
        self.servers.clear()

    def _goal_callback(self, _goal_request: Any) -> Any:
        if self.provider is None:
            return self._goal_response.REJECT
        return self._goal_response.ACCEPT

    def _cancel_callback(self, goal_handle: Any) -> Any:
        provider = self.provider
        if provider is None:
            return self._cancel_response.REJECT
        job_id = getattr(goal_handle, '_inspection_job_id', '')
        if job_id:
            try:
                provider.cancel(job_id, {'username': 'ros_action_bridge', 'role': 'admin'})
            except Exception:
                pass
        return self._cancel_response.ACCEPT

    def _make_execute_callback(self, kind: str, action_type: Any):
        async def _execute(goal_handle: Any) -> Any:
            provider = self.provider
            result_msg = action_type.Result()
            if provider is None:
                goal_handle.abort()
                result_msg.accepted = False
                result_msg.message = 'action_provider_unavailable'
                return result_msg
            payload = payload_from_goal(kind, goal_handle.request)
            validation_error = validate_action_payload(kind, payload)
            if validation_error:
                goal_handle.abort()
                result_msg.accepted = False
                result_msg.message = validation_error
                return result_msg
            job = provider.submit(kind, payload, {'username': 'ros_action_bridge', 'role': 'admin'})
            job_id = str(job.get('jobId', ''))
            setattr(goal_handle, '_inspection_job_id', job_id)
            started = time.monotonic()
            timeout_override: dict[str, Any] | None = None
            while True:
                current = provider.get_job(job_id) or {}
                status = str(current.get('status', ''))
                feedback = action_type.Feedback()
                feedback.phase = status or 'UNKNOWN'
                feedback.progress = _safe_float(current.get('progress', 0), default=0.0) / 100.0
                feedback.detail_json = json.dumps(current, ensure_ascii=False)
                goal_handle.publish_feedback(feedback)
                if goal_handle.is_cancel_requested:
                    provider.cancel(job_id, {'username': 'ros_action_bridge', 'role': 'admin'})
                if status in {'COMPLETED', 'FAILED', 'CANCELLED'}:
                    break
                if time.monotonic() - started > self.job_timeout_sec:
                    provider.cancel(job_id, {'username': 'ros_action_bridge', 'role': 'admin'})
                    timeout_override = {**(provider.get_job(job_id) or current), 'status': 'FAILED', 'message': 'action_job_timeout'}
                    break
                await asyncio.sleep(self.poll_interval_sec)
            current = timeout_override or provider.get_job(job_id) or {}
            status = str(current.get('status', ''))
            result = dict(current.get('result', {}))
            if status == 'COMPLETED':
                goal_handle.succeed()
            elif status == 'CANCELLED':
                goal_handle.canceled()
            else:
                goal_handle.abort()
            result_msg.accepted = status == 'COMPLETED'
            result_msg.message = str(current.get('message', status or 'UNKNOWN'))
            if hasattr(result_msg, 'export_url'):
                result_msg.export_url = str(result.get('exportUrl', result.get('export_url', '')))
            return result_msg
        return _execute

