from __future__ import annotations

import time

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import CaptureRequest, ControlCommand, FaultRaisedEvent, FsmTransitionEvent, VisionFrameAcquiredEvent
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    CaptureRequest = ControlCommand = FaultRaisedEvent = FsmTransitionEvent = VisionFrameAcquiredEvent = None

from inspection_interfaces.msg import CountStats, FaultEvent, InspectionResult, SortCommand, StationState
from inspection_interfaces.srv import ResetFault, StartInspection
from inspection_utils.transport_common import (
    MANUAL_STEP_CAPTURE_COMMAND,
    MANUAL_STEP_FEED_COMMAND,
    MANUAL_STEP_SORT_COMMAND,
)
from inspection_utils.logging_common import event_to_json
from inspection_utils.runtime_common import ManagedNodeMixin
from inspection_utils.runtime_common import qos_profile
from inspection_utils.config_common import parameter_as_bool
from inspection_utils.runtime_common import InspectionRuntimeNode
from inspection_utils.runtime_common import assert_typed_interfaces_available
from inspection_utils.transport_common import CAPTURE_REQUEST_TOPIC_TYPED, CONTROL_TOPIC_TYPED
from inspection_utils.runtime_event_contracts import (
    FAULT_RAISED_TOPIC_TYPED,
    FSM_TRANSITION_TOPIC_TYPED,
    VISION_FRAME_ACQUIRED_TOPIC_TYPED,
    populate_fault_raised_message,
    populate_fsm_transition_message,
    publish_dual_runtime_event,
)
from inspection_utils.station_common import DECISION_OUTPUT_TOPIC, SORT_REQUEST_LEGACY_TOPIC, SORT_REQUEST_TOPIC
from .fsm_core import (
    FSMData,
    StationEvent,
    StationPhase,
    transition,
)
from .runtime_context import RuntimeContext
from .fsm_egress import FsmEgressPublisher
from .fsm_ingress import FsmIngressAdapter
from .fsm_metrics import FsmMetricsService
from .phase_runtime import FSMPhaseRuntimeSupport


class FSMNode(ManagedNodeMixin, InspectionRuntimeNode):
    def __init__(self) -> None:
        super().__init__('inspection_fsm_node')
        self.declare_parameter('auto_start', False)
        self.declare_parameter('feed_timeout_sec', 1.5)
        self.declare_parameter('position_timeout_sec', 3.0)
        self.declare_parameter('capture_frame_timeout_sec', 1.0)
        self.declare_parameter('capture_timeout_sec', 1.0)
        self.declare_parameter('analyze_timeout_sec', 2.0)
        self.declare_parameter('decision_timeout_sec', 1.0)
        self.declare_parameter('sort_ack_timeout_sec', 1.5)
        self.declare_parameter('sort_done_timeout_sec', 3.0)
        self.declare_parameter('sort_timeout_sec', 3.0)
        self.declare_parameter('recovery_timeout_sec', 2.0)
        self.declare_parameter('feed_retry_limit', 1)
        self.declare_parameter('capture_retry_limit', 1)
        self.declare_parameter('analyze_retry_limit', 1)
        self.declare_parameter('sort_retry_limit', 1)
        self.declare_parameter('auto_self_check_pass', True)
        self.declare_parameter('auto_recovery_pass', True)
        self.declare_parameter('allow_manual_mode', True)
        self.declare_parameter('publish_legacy_sort_cmd', False)
        self.data = FSMData(phase=StationPhase.IDLE)
        self.declare_parameter('profile_name', 'production')
        self.runtime = RuntimeContext(profile_name=str(self.get_parameter('profile_name').value))
        self.phase_start = time.monotonic()
        self.cycle_start: float | None = None
        self.phase_timings_ms: dict[str, float] = {}
        self.feed_pub = self.create_publisher(String, '/station/feed_request', qos_profile('control'))
        self.capture_pub = self.create_publisher(String, '/inspection/capture_request', qos_profile('control'))
        self.typed_capture_pub = self.create_publisher(CaptureRequest, CAPTURE_REQUEST_TOPIC_TYPED, qos_profile('control')) if CaptureRequest is not None else None
        self.sort_pub = self.create_publisher(SortCommand, SORT_REQUEST_TOPIC, qos_profile('control'))
        self.publish_legacy_sort_cmd = parameter_as_bool(self, 'publish_legacy_sort_cmd', default=False)
        self.legacy_sort_pub = self.create_publisher(SortCommand, SORT_REQUEST_LEGACY_TOPIC, qos_profile('control')) if self.publish_legacy_sort_cmd else None
        self.reset_pub = self.create_publisher(String, '/station/reset_request', qos_profile('control'))
        self.event_pub = self.create_publisher(String, '/inspection/events', qos_profile('event'))
        self.typed_fsm_transition_pub = self.create_publisher(FsmTransitionEvent, FSM_TRANSITION_TOPIC_TYPED, qos_profile('event')) if FsmTransitionEvent is not None else None
        self.typed_fault_raised_pub = self.create_publisher(FaultRaisedEvent, FAULT_RAISED_TOPIC_TYPED, qos_profile('event')) if FaultRaisedEvent is not None else None
        self.count_pub = self.create_publisher(CountStats, '/station/count_stats', qos_profile('status'))
        self.fault_pub = self.create_publisher(FaultEvent, '/station/fault', qos_profile('fault'))
        self.state_sub = self.create_subscription(StationState, '/station/state', self.on_station_state, qos_profile('status'))
        self.result_sub = self.create_subscription(InspectionResult, '/inspection/result', self.on_result, qos_profile('status'))
        self.sort_sub = self.create_subscription(SortCommand, DECISION_OUTPUT_TOPIC, self.on_decision_output, qos_profile('control'))
        self.event_sub = self.create_subscription(String, '/inspection/events', self.on_event_message, qos_profile('event'))
        self.typed_vision_event_sub = self.create_subscription(VisionFrameAcquiredEvent, VISION_FRAME_ACQUIRED_TOPIC_TYPED, self.on_typed_vision_event_message, qos_profile('event')) if VisionFrameAcquiredEvent is not None else None
        self.control_sub = self.create_subscription(String, '/inspection/control', self.on_control_message, qos_profile('control'))
        self.typed_control_sub = self.create_subscription(ControlCommand, CONTROL_TOPIC_TYPED, self.on_typed_control_message, qos_profile('control')) if ControlCommand is not None else None
        self.create_service(StartInspection, '/inspection/start', self.on_start)
        self.create_service(ResetFault, '/inspection/reset_fault', self.on_reset_fault)
        self.stats = {'total': 0, 'ok': 0, 'ng': 0, 'recheck': 0, 'cycle_times': []}
        self.current_decision: str | None = None
        self.last_sort_cmd: SortCommand | None = None
        self.last_result_detail: dict[str, object] = {}
        self.egress = FsmEgressPublisher(self)
        self.ingress = FsmIngressAdapter(self)
        self.metrics = FsmMetricsService(self)
        self.phase_runtime = FSMPhaseRuntimeSupport(self)
        self.timer = self.create_timer(0.05, self.tick)
        assert_typed_interfaces_available(consumer='inspection_fsm_node', symbols={'CaptureRequest': CaptureRequest, 'ControlCommand': ControlCommand, 'FaultRaisedEvent': FaultRaisedEvent, 'FsmTransitionEvent': FsmTransitionEvent, 'VisionFrameAcquiredEvent': VisionFrameAcquiredEvent})
        self.setup_managed_runtime(node_name='inspection_fsm_node')

    def on_configure(self) -> tuple[bool, str]:
        return True, 'fsm configured'

    def on_activate(self) -> tuple[bool, str]:
        """Activate the FSM runtime without bypassing gateway start authority.

        Returns:
            A managed-runtime activation tuple.

        Boundary behavior:
            ``auto_start`` is treated as a legacy compatibility knob. When it is
            enabled while no ``recipe_id``/``batch_id`` binding exists, the node
            refuses to self-start and emits an audit event instead of inventing
            runtime authority locally.
        """
        if parameter_as_bool(self, 'auto_start', default=False):
            if self.data.phase != StationPhase.IDLE:
                self.emit_event('fsm_autostart_ignored', reason='phase_not_idle', actual_phase=self.data.phase.value)
            elif not str(self.data.recipe_id or '').strip() or not str(self.data.batch_id or '').strip():
                self.emit_event('fsm_autostart_rejected', reason='missing_gateway_binding')
            else:
                self.apply_event(StationEvent.START, 'managed_runtime_activate')
        return True, 'fsm active'

    def on_deactivate(self) -> tuple[bool, str]:
        return True, 'fsm inactive'

    def on_cleanup(self) -> tuple[bool, str]:
        return True, 'fsm cleaned'

    def on_shutdown(self) -> tuple[bool, str]:
        return True, 'fsm shutdown'

    def _runtime_input_blocked(self, source: str) -> bool:
        if not hasattr(self, 'lifecycle_runtime'):
            return False
        if self.is_active():
            return False
        self.emit_event('fsm_input_ignored', source=source, lifecycle_state=self.lifecycle_state)
        return True

    def _runtime_service_blocked(self, service_name: str) -> bool:
        """Reject service-plane state mutations while the managed runtime is inactive.

        Args:
            service_name: Canonical service endpoint used for audit events.

        Returns:
            ``True`` when the request must be rejected because the node is not
            in the ACTIVE lifecycle state; otherwise ``False``.

        Boundary behavior:
            The guard mirrors ``_runtime_input_blocked`` so service callbacks
            cannot mutate FSM state while the managed runtime is configuring,
            inactive, or shutting down.
        """
        if not hasattr(self, 'lifecycle_runtime'):
            return False
        if self.is_active():
            return False
        self.emit_event('fsm_service_rejected', service=service_name, lifecycle_state=self.lifecycle_state)
        return True

    def _event_to_json(self, event_type: str, **payload: object) -> str:
        """Build a canonical runtime event payload for FSM publications."""
        return event_to_json(
            event_type,
            node='inspection_fsm_node',
            phase=self.data.phase.value,
            item_id=self.data.item_id,
            batch_id=self.data.batch_id,
            recipe_id=self.data.recipe_id,
            trace_id=self.data.trace_id,
            cycle_index=self.data.cycle_index,
            runtime_phase=self.runtime.current.current_phase or self.data.phase.value,
            profile_name=self.runtime.profile_name,
            **payload,
        )

    def emit_event(self, event_type: str, **payload) -> None:
        payload_json = self._event_to_json(event_type, **payload)
        if event_type == 'fsm_transition':
            publish_dual_runtime_event(
                event_type='fsm_transition',
                legacy_publisher=self.event_pub,
                typed_publisher=self.typed_fsm_transition_pub,
                typed_message_cls=FsmTransitionEvent,
                populate_message=populate_fsm_transition_message,
                payload=safe_json_loads(payload_json),
            )
            return
        if event_type == 'fault_raised':
            publish_dual_runtime_event(
                event_type='fault_raised',
                legacy_publisher=self.event_pub,
                typed_publisher=self.typed_fault_raised_pub,
                typed_message_cls=FaultRaisedEvent,
                populate_message=populate_fault_raised_message,
                payload=safe_json_loads(payload_json),
            )
            return
        msg = String()
        msg.data = payload_json
        self.event_pub.publish(msg)

    def _record_phase_duration(self, phase: StationPhase, elapsed: float) -> None:
        self._metrics_service().record_phase_duration(phase, elapsed)

    def _egress_service(self) -> FsmEgressPublisher:
        if not hasattr(self, 'egress'):
            self.egress = FsmEgressPublisher(self)
        return self.egress

    def _ingress_service(self) -> FsmIngressAdapter:
        if not hasattr(self, 'ingress'):
            self.ingress = FsmIngressAdapter(self)
        return self.ingress

    def _metrics_service(self) -> FsmMetricsService:
        if not hasattr(self, 'metrics'):
            self.metrics = FsmMetricsService(self)
        return self.metrics

    def _run_command(self, command: str) -> None:
        self.phase_runtime.run_command(command)

    def apply_event(self, event: StationEvent, reason: str) -> None:
        prev_phase = self.data.phase
        elapsed = time.monotonic() - self.phase_start
        result = transition(self.data, event, reason)
        if not result.changed:
            self.emit_event('fsm_event_ignored', event=event.value, reason=reason, from_phase=prev_phase.value, guard_or_detail=result.reason)
            return
        self._record_phase_duration(prev_phase, elapsed)
        transition_snapshot = {
            'from_phase': prev_phase.value,
            'to_phase': self.data.phase.value,
            'event': event.value,
            'reason': reason,
            'phase_elapsed_ms': round(elapsed * 1000.0, 3),
            'retry_counts': dict(self.data.retry_counts),
            'manual_mode_enabled': self.data.manual_mode_enabled,
            'heartbeat_ok': self.data.heartbeat_ok,
        }
        self.runtime.current.current_phase = self.data.phase.value
        self.runtime.current.phase_timings_ms = dict(self.phase_timings_ms)
        self.runtime.current.retry_counts = dict(self.data.retry_counts)
        self.phase_start = time.monotonic()
        for command in result.commands:
            self._run_command(command)
        transition_snapshot['runtime'] = self.runtime.current.snapshot()
        self.emit_event('fsm_transition', **transition_snapshot)
        self._dispatch_phase_entry()

    def _dispatch_phase_entry(self) -> None:
        self.phase_runtime.dispatch_phase_entry()

    def publish_feed_request(self) -> None:
        self._egress_service().publish_feed_request()

    def publish_capture_request(self) -> None:
        self._egress_service().publish_capture_request()

    def publish_sort_request(self) -> None:
        self._egress_service().publish_sort_request()

    def publish_reset_request(self) -> None:
        self._egress_service().publish_reset_request()

    def on_start(self, request, response):
        """Accept a gateway-authored runtime start request.

        Args:
            request: ``StartInspection`` service request populated by the gateway
                control plane. ``recipe_id`` and ``batch_id`` are both required
                because the runtime no longer invents recipe authority locally.
            response: Mutable ``StartInspection`` service response.

        Returns:
            The populated response object.

        Raises:
            No exception is raised intentionally; validation failures are
            returned in-band through ``response.success`` and ``response.message``.

        Boundary behavior:
            The method fails closed when the caller omits ``recipe_id`` or
            ``batch_id`` so direct service callers cannot bypass the gateway's
            preflight and activation-truth checks.
        """
        if self._runtime_service_blocked('/inspection/start'):
            response.success = False
            response.message = 'runtime is not active'
            return response
        recipe_id = str(getattr(request, 'recipe_id', '') or '').strip()
        batch_id = str(getattr(request, 'batch_id', '') or '').strip()
        if not recipe_id:
            response.success = False
            response.message = 'recipe_id is required'
            self.emit_event('fsm_start_rejected', reason='recipe_id_missing')
            return response
        if not batch_id:
            response.success = False
            response.message = 'batch_id is required'
            self.emit_event('fsm_start_rejected', reason='batch_id_missing', requested_recipe_id=recipe_id)
            return response
        self.data.recipe_id = recipe_id
        self.data.batch_id = batch_id
        self.runtime.current.recipe_id = recipe_id
        self.runtime.current.batch_id = batch_id
        self.apply_event(StationEvent.START, 'service_start')
        response.success = True
        response.message = 'inspection started'
        return response

    def on_reset_fault(self, request, response):
        """Reset a latched fault only when the managed runtime is active."""
        if self._runtime_service_blocked('/inspection/reset_fault'):
            response.success = False
            response.message = 'runtime is not active'
            return response
        self.apply_event(StationEvent.RESET, f'reset_by_{request.operator_name}')
        response.success = True
        response.message = 'fault reset'
        return response

    def on_control_message(self, msg: String) -> None:
        """Apply an external control command to the station FSM."""
        self._ingress_service().on_control_message(msg)

    def on_typed_control_message(self, msg: object) -> None:
        self._ingress_service().on_typed_control_message(msg)

    def _drop_mismatched_payload(self, event_name: str, payload: dict, *, station_state: bool = False) -> bool:
        return self._ingress_service()._drop_mismatched_payload(event_name, payload, station_state=station_state)

    def on_event_message(self, msg: String) -> None:
        self._ingress_service().on_event_message(msg)

    def on_station_state(self, msg: StationState) -> None:
        self._ingress_service().on_station_state(msg)

    def on_result(self, msg: InspectionResult) -> None:
        self._ingress_service().on_result(msg)

    def on_decision_output(self, msg: SortCommand) -> None:
        self._ingress_service().on_decision_output(msg)

    def finish_cycle(self) -> None:
        self._metrics_service().finish_cycle()

    def raise_fault(self, code: str, description: str, event: StationEvent = StationEvent.FAULT) -> None:
        fault = FaultEvent()
        fault.stamp = self.get_clock().now().to_msg()
        fault.level = 'ERROR'
        fault.fault_code = code
        fault.source_node = 'inspection_fsm_node'
        fault.description = description
        fault.recoverable = True
        self.fault_pub.publish(fault)
        self.runtime.current.last_fault_code = code
        self.emit_event('fault_raised', code=code, description=description, runtime=self.runtime.current.snapshot())
        self.apply_event(event, code)

    def _retry_limit_for_phase(self, phase: StationPhase) -> int:
        return self.phase_runtime.retry_limit_for_phase(phase)

    def _retry_current_phase(self) -> bool:
        return self.phase_runtime.retry_current_phase()

    def tick(self) -> None:
        self.phase_runtime.tick()


def main() -> None:
    rclpy.init()
    node = FSMNode()
    try:
        rclpy.spin(node)
    finally:
        try:
            node.on_shutdown()
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()
