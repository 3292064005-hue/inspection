from __future__ import annotations

import json
import threading
import uuid
from typing import Any

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import ActionExecutorEvent, ControlCommand
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    ActionExecutorEvent = ControlCommand = None

from inspection_interfaces.srv import ResetFault, StartInspection
from inspection_utils.control_protocol import normalize_control_command
from inspection_utils.managed_node import ManagedNodeMixin
from inspection_utils.param_parsing import parameter_as_bool
from inspection_utils.paths import resolve_resource_path, resolve_runtime_path
from inspection_utils.qos import qos_profile
from inspection_utils.runtime_node import InspectionRuntimeNode
from inspection_utils.transport_adapters import legacy_payload_json_from_typed_message, publish_dual_control
from inspection_utils.typed_interfaces import assert_typed_interfaces_available
from inspection_utils.transport_contracts import ACTION_EXECUTOR_EVENT_TOPIC_TYPED, CONTROL_TOPIC_TYPED, action_executor_event_payload

from .action_contract import EXECUTOR_CANCEL_TOPIC, EXECUTOR_EVENT_TOPIC, EXECUTOR_SUBMIT_TOPIC, ActionPolicyError, ensure_action_submit_allowed
from .action_execution_runtime import ActionExecutionRuntime
from .export_service import BatchExportService
from .recipe_store import RecipeStore
from .replay_service import ReplayService
from .result_store import ResultStore
from .ros_action_bridge import ActionProvider, RosActionBridge
from .runtime_components import RosServiceInvoker, ServiceCallResult, utc_now


def _safe_json_loads(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw or '{}')
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


class ActionExecutorNode(ManagedNodeMixin, InspectionRuntimeNode):
    """Independent ROS node that owns long-running action execution.

    The gateway persists job state and exposes HTTP/API surfaces, while this
    node receives execution requests over internal ROS topics, runs the
    independent execution runtime, and streams job updates back over ROS.

    Native ROS action servers are also hosted here so action transport and
    execution are layered inside the executor node instead of the gateway.
    """

    def __init__(self) -> None:
        super().__init__('inspection_action_executor_node')
        self.declare_parameter('log_root', 'logs/runtime')
        self.declare_parameter('recipe_root', 'config/recipes')
        self.declare_parameter('max_workers', 4)
        self.declare_parameter('native_action_server_enabled', True)
        self.log_root = resolve_runtime_path(str(self.get_parameter('log_root').value), start=__file__)
        self.recipe_root = resolve_runtime_path(str(self.get_parameter('recipe_root').value), start=__file__)
        self.recipe_store = RecipeStore(self.recipe_root)
        self.result_store = ResultStore(self.log_root)
        self.replay = ReplayService(self.log_root)
        self.exporter = BatchExportService(log_root=self.log_root, result_store=self.result_store, recipe_store=self.recipe_store)
        self.service_invoker = RosServiceInvoker()
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

        self.control_pub = self.create_publisher(String, '/inspection/control', qos_profile('control'))
        self.typed_control_pub = self.create_publisher(ControlCommand, CONTROL_TOPIC_TYPED, qos_profile('control')) if ControlCommand is not None else None
        self.events_pub = self.create_publisher(String, EXECUTOR_EVENT_TOPIC, qos_profile('event'))
        self.typed_events_pub = self.create_publisher(ActionExecutorEvent, ACTION_EXECUTOR_EVENT_TOPIC_TYPED, qos_profile('event')) if ActionExecutorEvent is not None else None
        self.create_subscription(String, EXECUTOR_SUBMIT_TOPIC, self.on_submit_message, qos_profile('event'))
        self.create_subscription(String, EXECUTOR_CANCEL_TOPIC, self.on_cancel_message, qos_profile('control'))
        self.start_client = self.create_client(StartInspection, '/inspection/start')
        self.reset_client = self.create_client(ResetFault, '/inspection/reset_fault')
        self.runtime = ActionExecutionRuntime(self, max_workers=int(self.get_parameter('max_workers').value or 4))
        self.native_action_bridge = RosActionBridge(self, enable_servers=parameter_as_bool(self, 'native_action_server_enabled', default=True))
        self.native_action_bridge.register_provider(
            ActionProvider(
                submit=self.submit_native_action_job,
                get_job=self.get_native_action_job,
                cancel=self.cancel_native_action_job,
            )
        )
        assert_typed_interfaces_available(consumer='inspection_action_executor_node', symbols={'ActionExecutorEvent': ActionExecutorEvent, 'ControlCommand': ControlCommand})
        self.setup_managed_runtime(node_name='inspection_action_executor_node')

    def on_configure(self):
        return True, 'action executor configured'

    def on_activate(self):
        return True, 'action executor active'

    def on_deactivate(self):
        return True, 'action executor inactive'

    def on_shutdown(self):
        try:
            destroy_bridge = getattr(self.native_action_bridge, 'destroy', None)
            if callable(destroy_bridge):
                destroy_bridge()
        finally:
            self.runtime.shutdown()
        return True, 'action executor shutdown'

    # Context adapter methods consumed by ActionExecutionRuntime
    def node(self) -> 'ActionExecutorNode':
        return self

    def replay_service(self) -> ReplayService:
        return self.replay

    def export_service(self) -> BatchExportService:
        return self.exporter

    def audit(self, **_payload: Any) -> None:
        return None

    def refresh_recipes(self) -> list[dict[str, Any]]:
        default_recipe = self.recipe_store.current_default()
        active_recipe_id = str(default_recipe.get('recipe_id', '')) if isinstance(default_recipe, dict) else ''
        return [self.recipe_store.to_hmi_profile(recipe, active_recipe_id=active_recipe_id) for recipe in self.recipe_store.load_all()]

    def new_batch(self) -> str:
        return f"BATCH-{utc_now().replace(':', '').replace('-', '').replace('T', '-').replace('Z', '')}"

    def publish_control(self, action: str) -> None:
        publish_dual_control(
            legacy_publisher=self.control_pub,
            typed_publisher=self.typed_control_pub,
            typed_message_cls=ControlCommand,
            command=normalize_control_command(action),
            source='inspection_action_executor_node',
            event_type='action_executor_control',
        )

    def _handle_service_result(self, result: ServiceCallResult) -> tuple[bool, str]:
        return result.ok, result.message

    def call_start(self) -> tuple[bool, str]:
        request = StartInspection.Request()
        default_recipe = self.recipe_store.current_default()
        request.recipe_id = str(default_recipe.get('recipe_id', 'default_recipe')) if isinstance(default_recipe, dict) else 'default_recipe'
        request.batch_id = self.new_batch()
        result = self.service_invoker.call(
            self.start_client,
            request,
            service_name='/inspection/start',
            unavailable_message='未找到 /inspection/start 服务。',
            timeout_message='启动请求超时。',
        )
        return self._handle_service_result(result)

    def reset_fault(self) -> tuple[bool, str]:
        request = ResetFault.Request()
        request.operator_name = 'action_executor'
        request.comment = 'reset_from_action_executor'
        result = self.service_invoker.call(
            self.reset_client,
            request,
            service_name='/inspection/reset_fault',
            unavailable_message='未找到 /inspection/reset_fault 服务。',
            timeout_message='故障复位请求超时。',
        )
        if not result.ok and result.message == '未找到 /inspection/reset_fault 服务。':
            self.publish_control('reset')
            return True, '已退回控制话题复位。'
        return self._handle_service_result(result)

    def _next_job_id(self, kind: str) -> str:
        return f"{str(kind).strip().lower()}-{uuid.uuid4().hex[:12]}"

    def _normalize_actor(self, actor: dict[str, Any] | None) -> dict[str, Any]:
        actor = actor or {}
        return {
            'username': str(actor.get('username', 'executor')),
            'role': str(actor.get('role', 'system')),
        }

    def _queue_job(self, job_id: str, kind: str, job_payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        """Queue an executor-owned action job after policy validation.

        Args:
            job_id: Persisted or transport-provided job identifier.
            kind: Action kind.
            job_payload: Decoded action payload.
            actor: Normalized actor metadata.

        Returns:
            The queued job snapshot.

        Raises:
            PermissionError: When the catalog marks the action as non-executable.
            KeyError: When the action kind is unknown.

        Boundary behavior:
            Existing job ids are treated as idempotent replays and returned as-is
            without creating duplicate worker submissions.
        """
        normalized_job_id = str(job_id or '').strip()
        normalized_kind = str(kind or '').strip().lower()
        with self._lock:
            existing = self._jobs.get(normalized_job_id)
            if isinstance(existing, dict):
                return dict(existing)
        contract = ensure_action_submit_allowed(normalized_kind)
        payload = {
            'jobId': normalized_job_id,
            'kind': normalized_kind,
            'status': 'QUEUED',
            'progress': 0,
            'message': '任务已排队。',
            'payload': dict(job_payload),
            'requestedBy': str(actor.get('username', 'anonymous')),
            'requestedRole': str(actor.get('role', 'viewer')),
            'actionTopic': contract.topic,
            'actionType': contract.ros_type,
            'capability': contract.capability.to_dict(),
            'feedback': {'phase': 'QUEUED', 'progress': 0.0, 'detail': {'message': '任务已排队。'}},
        }
        with self._lock:
            self._jobs[normalized_job_id] = dict(payload)
        self._publish_event_payload(payload)
        self.runtime.submit(normalized_job_id, normalized_kind, payload=dict(job_payload), actor=dict(actor), update=self._publish_update)
        return dict(payload)

    def submit_native_action_job(self, kind: str, payload: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
        return self._queue_job(self._next_job_id(kind), kind, dict(payload), self._normalize_actor(actor))

    def get_native_action_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            payload = self._jobs.get(str(job_id), None)
        return None if payload is None else dict(payload)

    def _request_cancel(self, job_id: str, *, source: str) -> bool:
        flag, future = self.runtime.cancel(job_id)
        if future is not None and future.cancel():
            self._publish_update(job_id, status='CANCELLED', completedAt=utc_now(), message=f'任务已在执行前取消。({source})')
            return True
        if flag is not None:
            self._publish_update(job_id, status='CANCELLING', message=f'已请求取消，等待任务响应。({source})')
            return True
        return False

    def cancel_native_action_job(self, job_id: str, _actor: dict[str, Any]) -> dict[str, Any]:
        self._request_cancel(job_id, source='native_action')
        payload = self.get_native_action_job(job_id)
        return payload or {'jobId': str(job_id), 'status': 'UNKNOWN'}

    # ROS topic handlers
    def on_submit_message(self, msg: String) -> None:
        payload = _safe_json_loads(msg.data)
        job_id = str(payload.get('jobId', '')).strip()
        kind = str(payload.get('kind', '')).strip()
        if not job_id or not kind:
            return
        actor = self._normalize_actor(payload.get('actor', {}) if isinstance(payload.get('actor', {}), dict) else {})
        job_payload = payload.get('payload', {}) if isinstance(payload.get('payload', {}), dict) else {}
        try:
            self._queue_job(job_id, kind, job_payload, actor)
        except ActionPolicyError as exc:
            self._publish_event_payload({
                'jobId': job_id,
                'kind': str(kind).strip().lower(),
                'status': 'FAILED',
                'message': '动作执行被策略拒绝。',
                'error': exc.to_payload(),
                'completedAt': utc_now(),
            })
        except Exception as exc:
            self._publish_event_payload({
                'jobId': job_id,
                'kind': str(kind).strip().lower(),
                'status': 'FAILED',
                'message': str(exc),
                'error': {'message': str(exc)},
                'completedAt': utc_now(),
            })

    def on_cancel_message(self, msg: String) -> None:
        payload = _safe_json_loads(msg.data)
        job_id = str(payload.get('jobId', '')).strip()
        if not job_id:
            return
        self._request_cancel(job_id, source='transport')

    def _publish_event_payload(self, payload: dict[str, Any]) -> None:
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.events_pub.publish(msg)
        if self.typed_events_pub is not None and ActionExecutorEvent is not None:
            typed_payload = action_executor_event_payload(payload)
            typed = ActionExecutorEvent()
            typed.job_id = str(typed_payload.get('jobId', ''))
            typed.kind = str(typed_payload.get('kind', ''))
            typed.status = str(typed_payload.get('status', ''))
            typed.source = str(typed_payload.get('source', 'inspection_action_executor_node'))
            typed.schema_version = str(typed_payload.get('schema_version', 'v1') or 'v1')
            typed.payload_json = legacy_payload_json_from_typed_message(typed, default_event_type='action_executor_event', fallback=payload)
            self.typed_events_pub.publish(typed)

    def _publish_update(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            current = dict(self._jobs.get(job_id, {'jobId': job_id}))
            current.update(fields)
            self._jobs[job_id] = current
            payload = dict(current)
        self._publish_event_payload(payload)


def main(args: list[str] | None = None) -> None:
    rclpy.init(args=args)
    node = ActionExecutorNode()
    try:
        rclpy.spin(node)
    finally:
        try:
            node.on_shutdown()
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()
