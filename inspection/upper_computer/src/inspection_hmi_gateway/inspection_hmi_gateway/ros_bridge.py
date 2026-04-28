from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import json

from std_msgs.msg import String

try:
    from inspection_interfaces.msg import (
        ActionExecutorEvent,
        BridgeHandshakeCompleteEvent,
        BridgeHeartbeatEvent,
        CaptureRequest,
        ControlCommand,
        DecisionPublishedEvent,
        DiagnosticsSnapshot,
        FaultRaisedEvent,
        FsmTransitionEvent,
        SupervisorCommand,
        SupervisorStateEnvelope,
        VisionFrameAcquiredEvent,
    )
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    ActionExecutorEvent = BridgeHandshakeCompleteEvent = BridgeHeartbeatEvent = CaptureRequest = ControlCommand = DecisionPublishedEvent = DiagnosticsSnapshot = FaultRaisedEvent = FsmTransitionEvent = SupervisorCommand = SupervisorStateEnvelope = VisionFrameAcquiredEvent = None

from inspection_interfaces.msg import CountStats, FaultEvent, InspectionResult, StationState
from inspection_interfaces.srv import ResetFault, StartInspection
from inspection_utils.transport_common import normalize_control_command
from inspection_utils.logging_common import safe_json_loads
from inspection_utils.transport_common import legacy_payload_json_from_typed_message, publish_dual_capture_request, publish_dual_control, publish_dual_supervisor_command
from inspection_utils.runtime_event_contracts import (
    BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED,
    BRIDGE_HEARTBEAT_TOPIC_TYPED,
    DECISION_PUBLISHED_TOPIC_TYPED,
    FAULT_RAISED_TOPIC_TYPED,
    FSM_TRANSITION_TOPIC_TYPED,
    RuntimeEventDeduper,
    VISION_FRAME_ACQUIRED_TOPIC_TYPED,
    is_runtime_event_payload,
    normalize_runtime_event_message,
)
from inspection_utils.runtime_common import assert_typed_interfaces_available
from inspection_utils.transport_common import (
    ACTION_EXECUTOR_EVENT_TOPIC_TYPED,
    CAPTURE_REQUEST_TOPIC_TYPED,
    CONTROL_TOPIC_TYPED,
    DIAGNOSTICS_TOPIC_TYPED,
    SUPERVISOR_COMMAND_TOPIC_TYPED,
    SUPERVISOR_STATE_TOPIC_TYPED,
)
from inspection_utils.runtime_common import qos_profile

from .action_contract import EXECUTOR_CANCEL_TOPIC, EXECUTOR_EVENT_TOPIC, EXECUTOR_SUBMIT_TOPIC
from .native_action_client import NativeActionClientAdapter
from .ros_action_bridge import ActionProvider, RosActionBridge
from .runtime_components import RosServiceInvoker, ServiceCallResult


@dataclass(slots=True)
class GatewaySubscriptionHandlers:
    """Callbacks used by :class:`GatewayRosBridge` for inbound ROS traffic."""

    on_count_stats: Callable[[CountStats], None]
    on_station_state: Callable[[StationState], None]
    on_result: Callable[[InspectionResult], None]
    on_fault: Callable[[FaultEvent], None]
    on_event: Callable[[str], None]
    on_diagnostics: Callable[[str], None]
    on_supervisor_state: Callable[[str], None]
    on_orchestrator_advice: Callable[[str], None]
    on_action_executor_event: Callable[[dict[str, Any]], None]


@dataclass(slots=True)
class GatewayRosBridgeMetrics:
    """Summarize ROS bridge transport activity."""

    published_control: int = 0
    published_capture_requests: int = 0
    published_supervisor_commands: int = 0
    submitted_executor_jobs: int = 0
    submitted_native_goals: int = 0
    cancelled_executor_jobs: int = 0
    cancelled_native_goals: int = 0
    received_executor_updates: int = 0
    service_failures: int = 0
    service_timeouts: int = 0
    subscriptions_bound: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'publishedControl': int(self.published_control),
            'publishedCaptureRequests': int(self.published_capture_requests),
            'publishedSupervisorCommands': int(self.published_supervisor_commands),
            'submittedExecutorJobs': int(self.submitted_executor_jobs),
            'submittedNativeGoals': int(self.submitted_native_goals),
            'cancelledExecutorJobs': int(self.cancelled_executor_jobs),
            'cancelledNativeGoals': int(self.cancelled_native_goals),
            'receivedExecutorUpdates': int(self.received_executor_updates),
            'serviceFailures': int(self.service_failures),
            'serviceTimeouts': int(self.service_timeouts),
            'subscriptionsBound': list(self.subscriptions_bound),
        }


class GatewayRosBridge:
    """Own publishers, subscriptions, service clients, and action bridging.

    This component isolates ROS transport wiring from business state and HMI
    projection. ``GatewayNode`` composes it with the projector and application
    facade so the gateway runtime is split into transport, projection, and
    service layers without changing the public API surface.
    """

    def __init__(
        self,
        node: Any,
        *,
        handlers: GatewaySubscriptionHandlers,
        executor_enabled: bool,
        service_invoker: RosServiceInvoker | None = None,
    ) -> None:
        self.node = node
        self.handlers = handlers
        self.service_invoker = service_invoker or RosServiceInvoker()
        self.metrics = GatewayRosBridgeMetrics()
        self.runtime_event_deduper = RuntimeEventDeduper(max_entries=512, ttl_sec=2.0)
        assert_typed_interfaces_available(consumer='inspection_hmi_gateway_bridge', symbols={'ActionExecutorEvent': ActionExecutorEvent, 'BridgeHandshakeCompleteEvent': BridgeHandshakeCompleteEvent, 'BridgeHeartbeatEvent': BridgeHeartbeatEvent, 'CaptureRequest': CaptureRequest, 'ControlCommand': ControlCommand, 'DecisionPublishedEvent': DecisionPublishedEvent, 'DiagnosticsSnapshot': DiagnosticsSnapshot, 'FaultRaisedEvent': FaultRaisedEvent, 'FsmTransitionEvent': FsmTransitionEvent, 'SupervisorCommand': SupervisorCommand, 'VisionFrameAcquiredEvent': VisionFrameAcquiredEvent})
        self._action_executor_update_handlers: list[Callable[[dict[str, Any]], None]] = []

        self.control_pub = node.create_publisher(String, '/inspection/control', qos_profile('control'))
        self.typed_control_pub = node.create_publisher(ControlCommand, CONTROL_TOPIC_TYPED, qos_profile('control')) if ControlCommand is not None else None
        self.capture_pub = node.create_publisher(String, '/inspection/capture_request', qos_profile('event'))
        self.typed_capture_pub = node.create_publisher(CaptureRequest, CAPTURE_REQUEST_TOPIC_TYPED, qos_profile('event')) if CaptureRequest is not None else None
        self.supervisor_command_pub = node.create_publisher(String, '/inspection/supervisor/command', qos_profile('control'))
        self.typed_supervisor_command_pub = node.create_publisher(SupervisorCommand, SUPERVISOR_COMMAND_TOPIC_TYPED, qos_profile('control')) if SupervisorCommand is not None else None
        self.action_executor_submit_pub = node.create_publisher(String, EXECUTOR_SUBMIT_TOPIC, qos_profile('event'))
        self.action_executor_cancel_pub = node.create_publisher(String, EXECUTOR_CANCEL_TOPIC, qos_profile('control'))
        self.start_client = node.create_client(StartInspection, '/inspection/start')
        self.reset_client = node.create_client(ResetFault, '/inspection/reset_fault')
        self.action_bridge = RosActionBridge(node, enable_servers=not executor_enabled)
        self.native_action_client = NativeActionClientAdapter(node)

        node.create_subscription(String, EXECUTOR_EVENT_TOPIC, self._on_action_executor_event, qos_profile('event'))
        if ActionExecutorEvent is not None:
            node.create_subscription(ActionExecutorEvent, ACTION_EXECUTOR_EVENT_TOPIC_TYPED, self._on_typed_action_executor_event, qos_profile('event'))
        node.create_subscription(CountStats, '/station/count_stats', handlers.on_count_stats, qos_profile('station_state'))
        node.create_subscription(StationState, '/station/state', handlers.on_station_state, qos_profile('station_state'))
        node.create_subscription(InspectionResult, '/inspection/result', handlers.on_result, qos_profile('result'))
        node.create_subscription(FaultEvent, '/station/fault', handlers.on_fault, qos_profile('event'))
        node.create_subscription(String, '/inspection/events', self._on_event_message, qos_profile('event'))
        if FsmTransitionEvent is not None:
            node.create_subscription(FsmTransitionEvent, FSM_TRANSITION_TOPIC_TYPED, self._on_typed_runtime_event_message, qos_profile('event'))
        if VisionFrameAcquiredEvent is not None:
            node.create_subscription(VisionFrameAcquiredEvent, VISION_FRAME_ACQUIRED_TOPIC_TYPED, self._on_typed_runtime_event_message, qos_profile('event'))
        if DecisionPublishedEvent is not None:
            node.create_subscription(DecisionPublishedEvent, DECISION_PUBLISHED_TOPIC_TYPED, self._on_typed_runtime_event_message, qos_profile('event'))
        if BridgeHeartbeatEvent is not None:
            node.create_subscription(BridgeHeartbeatEvent, BRIDGE_HEARTBEAT_TOPIC_TYPED, self._on_typed_runtime_event_message, qos_profile('event'))
        if BridgeHandshakeCompleteEvent is not None:
            node.create_subscription(BridgeHandshakeCompleteEvent, BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED, self._on_typed_runtime_event_message, qos_profile('event'))
        if FaultRaisedEvent is not None:
            node.create_subscription(FaultRaisedEvent, FAULT_RAISED_TOPIC_TYPED, self._on_typed_runtime_event_message, qos_profile('event'))
        node.create_subscription(String, '/inspection/diagnostics', self._on_diagnostics_message, qos_profile('diagnostics'))
        node.create_subscription(String, '/inspection/supervisor/state', self._on_supervisor_state_message, qos_profile('event'))
        node.create_subscription(String, '/inspection/orchestrator/advice', self._on_orchestrator_advice_message, qos_profile('event'))
        if DiagnosticsSnapshot is not None:
            node.create_subscription(DiagnosticsSnapshot, DIAGNOSTICS_TOPIC_TYPED, self._on_typed_diagnostics_message, qos_profile('diagnostics'))
        if SupervisorStateEnvelope is not None:
            node.create_subscription(SupervisorStateEnvelope, SUPERVISOR_STATE_TOPIC_TYPED, self._on_typed_supervisor_state_message, qos_profile('event'))
        self.metrics.subscriptions_bound = [
            EXECUTOR_EVENT_TOPIC,
            ACTION_EXECUTOR_EVENT_TOPIC_TYPED,
            '/station/count_stats',
            '/station/state',
            '/inspection/result',
            '/station/fault',
            '/inspection/events',
            FSM_TRANSITION_TOPIC_TYPED,
            VISION_FRAME_ACQUIRED_TOPIC_TYPED,
            DECISION_PUBLISHED_TOPIC_TYPED,
            BRIDGE_HEARTBEAT_TOPIC_TYPED,
            BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED,
            FAULT_RAISED_TOPIC_TYPED,
            '/inspection/diagnostics',
            '/inspection/supervisor/state',
            '/inspection/orchestrator/advice',
            DIAGNOSTICS_TOPIC_TYPED,
            SUPERVISOR_STATE_TOPIC_TYPED,
        ]

    def register_action_jobs(self, *, submit: Any, get_job: Any, cancel: Any) -> None:
        """Register higher-level action job handlers with the ROS action bridge."""
        self.action_bridge.register_provider(ActionProvider(submit=submit, get_job=get_job, cancel=cancel))

    def register_action_executor_updates(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback for executor status updates."""
        if callable(handler):
            self._action_executor_update_handlers.append(handler)

    def publish_control(self, action: str) -> None:
        """Publish a canonical control command."""
        normalized_action = normalize_control_command(action)
        publish_dual_control(
            legacy_publisher=self.control_pub,
            typed_publisher=self.typed_control_pub,
            typed_message_cls=ControlCommand,
            command=normalized_action,
            source='inspection_hmi_gateway',
            event_type='control_command',
        )
        self.metrics.published_control += 1

    def publish_capture_request(self, payload: dict[str, Any]) -> bool:
        """Publish a capture request to the vision subsystem."""
        if not isinstance(payload, dict):
            return False
        trace_id = str(payload.get('trace_id', payload.get('traceId', ''))).strip()
        if not trace_id:
            return False
        batch_id = str(payload.get('batch_id', payload.get('batchId', '')) or '')
        item_id = int(payload.get('item_id', payload.get('itemId', -1)) or -1)
        frame_index = int(payload.get('frame_index', payload.get('frameIndex', -1)) or -1)
        source = str(payload.get('source', 'inspection_hmi_gateway') or 'inspection_hmi_gateway')
        schema_version = str(payload.get('schema_version', 'v1') or 'v1')
        passthrough = {
            key: value
            for key, value in payload.items()
            if key not in {'trace_id', 'traceId', 'batch_id', 'batchId', 'item_id', 'itemId', 'frame_index', 'frameIndex', 'source', 'schema_version', 'type'}
        }
        event_type = str(payload.get('type', 'capture_request') or 'capture_request')
        publish_dual_capture_request(
            legacy_publisher=self.capture_pub,
            typed_publisher=self.typed_capture_pub,
            typed_message_cls=CaptureRequest,
            trace_id=trace_id,
            event_type=event_type,
            batch_id=batch_id,
            item_id=item_id,
            frame_index=frame_index,
            source=source,
            schema_version=schema_version,
            extra=passthrough,
        )
        self.metrics.published_capture_requests += 1
        return True

    def publish_supervisor_command(self, command: str, *, mode: str = '', reason: str = '') -> bool:
        """Publish one canonical supervisor command to the typed/legacy control plane.

        Args:
            command: Supervisor command name, for example ``set_mode``.
            mode: Optional target supervisor mode.
            reason: Optional audit-friendly reason string.

        Returns:
            ``True`` when the command envelope was published, ``False`` for an
            empty command name.

        Raises:
            No exception is intentionally raised here. Transport failures are
            delegated to the underlying ROS publishers.

        Boundary behavior:
            The legacy JSON topic remains published during migration, but the
            typed ``SupervisorCommand`` topic is now the canonical control-plane
            contract for new consumers.
        """
        normalized_command = str(command or '').strip().lower()
        if not normalized_command:
            return False
        publish_dual_supervisor_command(
            legacy_publisher=self.supervisor_command_pub,
            typed_publisher=self.typed_supervisor_command_pub,
            typed_message_cls=SupervisorCommand,
            command=normalized_command,
            target_mode=str(mode or '').upper(),
            reason=str(reason or ''),
            source='inspection_hmi_gateway',
            event_type='supervisor_command',
        )
        self.metrics.published_supervisor_commands += 1
        return True

    def submit_action_execution(self, payload: dict[str, Any]) -> bool:
        """Submit an action executor job payload."""
        if not isinstance(payload, dict) or not payload.get('jobId'):
            return False
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.action_executor_submit_pub.publish(msg)
        self.metrics.submitted_executor_jobs += 1
        return True

    def cancel_action_execution(self, job_id: str, actor: dict[str, Any]) -> bool:
        """Cancel an in-flight action executor job."""
        if not str(job_id or '').strip():
            return False
        msg = String()
        msg.data = json.dumps({'jobId': str(job_id), 'actor': dict(actor or {})}, ensure_ascii=False)
        self.action_executor_cancel_pub.publish(msg)
        self.metrics.cancelled_executor_jobs += 1
        return True

    def submit_native_action_goal(self, record: dict[str, Any], *, actor: dict[str, Any], update: Callable[..., None]) -> bool:
        """Dispatch a persisted job record through native ROS Action clients."""
        ok = self.native_action_client.submit(record, actor=dict(actor or {}), update=update)
        if ok:
            self.metrics.submitted_native_goals += 1
        return ok

    def cancel_native_action_goal(self, job_id: str, actor: dict[str, Any]) -> bool:
        """Cancel an in-flight native ROS action goal."""
        ok = self.native_action_client.cancel(job_id, dict(actor or {}))
        if ok:
            self.metrics.cancelled_native_goals += 1
        return ok

    def call_start(
        self,
        request: StartInspection.Request,
        *,
        unavailable_message: str,
        timeout_message: str,
    ) -> ServiceCallResult:
        """Invoke the inspection start service."""
        result = self.service_invoker.call(
            self.start_client,
            request,
            service_name='/inspection/start',
            unavailable_message=unavailable_message,
            timeout_message=timeout_message,
        )
        self._record_service_result(result, timeout_message=timeout_message)
        return result

    def call_reset_fault(
        self,
        request: ResetFault.Request,
        *,
        unavailable_message: str,
        timeout_message: str,
    ) -> ServiceCallResult:
        """Invoke the station fault-reset service."""
        result = self.service_invoker.call(
            self.reset_client,
            request,
            service_name='/inspection/reset_fault',
            unavailable_message=unavailable_message,
            timeout_message=timeout_message,
        )
        self._record_service_result(result, timeout_message=timeout_message)
        return result

    def snapshot(self) -> dict[str, Any]:
        """Return ROS bridge transport metrics."""
        return {**self.metrics.to_dict(), 'nativeActionClient': self.native_action_client.snapshot()}

    def _record_service_result(self, result: ServiceCallResult, *, timeout_message: str) -> None:
        if result.ok:
            return
        self.metrics.service_failures += 1
        if result.message == timeout_message:
            self.metrics.service_timeouts += 1

    def _forward_runtime_event_payload(self, payload: dict[str, Any]) -> None:
        if is_runtime_event_payload(payload) and self.runtime_event_deduper.seen_recently(payload):
            return
        self.handlers.on_event(json.dumps(payload, ensure_ascii=False, sort_keys=True))

    def _on_event_message(self, msg: String) -> None:
        payload = safe_json_loads(msg.data or '{}', {})
        if isinstance(payload, dict):
            self._forward_runtime_event_payload(payload)
            return
        self.handlers.on_event(msg.data)

    def _on_typed_runtime_event_message(self, msg: object) -> None:
        fallback_payload = safe_json_loads(getattr(msg, 'payload_json', '') or '{}', {})
        default_event_type = str(fallback_payload.get('type', '') or getattr(msg, 'event_type', '') or '').strip() or 'runtime_event'
        payload = normalize_runtime_event_message(msg, default_event_type=default_event_type)
        self._forward_runtime_event_payload(payload)

    def _on_diagnostics_message(self, msg: String) -> None:
        self.handlers.on_diagnostics(msg.data)

    def _on_supervisor_state_message(self, msg: String) -> None:
        self.handlers.on_supervisor_state(msg.data)

    def _on_orchestrator_advice_message(self, msg: String) -> None:
        self.handlers.on_orchestrator_advice(msg.data)

    def _on_typed_diagnostics_message(self, msg: Any) -> None:
        self.handlers.on_diagnostics(legacy_payload_json_from_typed_message(msg, default_event_type='diagnostics_snapshot', bridge_name='diagnostics'))

    def _on_typed_supervisor_state_message(self, msg: Any) -> None:
        self.handlers.on_supervisor_state(legacy_payload_json_from_typed_message(msg, default_event_type='supervisor_state', bridge_name='supervisor_state'))

    def _on_action_executor_event(self, msg: String) -> None:
        payload = safe_json_loads(msg.data or '{}')
        if not isinstance(payload, dict):
            return
        self.metrics.received_executor_updates += 1
        self.handlers.on_action_executor_event(dict(payload))
        for handler in list(self._action_executor_update_handlers):
            try:
                handler(dict(payload))
            except Exception:
                continue

    def _on_typed_action_executor_event(self, msg: Any) -> None:
        payload = safe_json_loads(legacy_payload_json_from_typed_message(msg, default_event_type='action_executor_event', bridge_name='action_executor_event'), {})
        if not isinstance(payload, dict):
            payload = {
                'jobId': str(getattr(msg, 'job_id', '')),
                'kind': str(getattr(msg, 'kind', '')),
                'status': str(getattr(msg, 'status', '')),
                'source': str(getattr(msg, 'source', '')),
                'schema_version': str(getattr(msg, 'schema_version', 'v1') or 'v1'),
            }
        self.metrics.received_executor_updates += 1
        self.handlers.on_action_executor_event(dict(payload))
        for handler in list(self._action_executor_update_handlers):
            try:
                handler(dict(payload))
            except Exception:
                continue
