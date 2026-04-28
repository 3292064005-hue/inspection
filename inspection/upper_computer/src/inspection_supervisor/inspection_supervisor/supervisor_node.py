from __future__ import annotations

import time

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import BridgeHandshakeCompleteEvent, BridgeHeartbeatEvent, ControlCommand, DecisionPublishedEvent, DiagnosticsSnapshot, FaultRaisedEvent, FsmTransitionEvent, SupervisorCommand, SupervisorStateEnvelope, VisionFrameAcquiredEvent
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    BridgeHandshakeCompleteEvent = BridgeHeartbeatEvent = ControlCommand = DecisionPublishedEvent = DiagnosticsSnapshot = FaultRaisedEvent = FsmTransitionEvent = SupervisorCommand = SupervisorStateEnvelope = VisionFrameAcquiredEvent = None

from inspection_utils.transport_common import (
    ENTER_MANUAL_COMMAND,
    PAUSE_COMMAND,
    EXIT_MANUAL_COMMAND,
    RESUME_COMMAND,
    STOP_COMMAND,
    normalize_control_command,
)
from inspection_utils.logging_common import event_to_json, safe_json_loads
from inspection_utils.runtime_common import ExternalServiceRuntimeMixin
from inspection_utils.runtime_common import StandardRuntimeNode
from inspection_utils.transport_common import normalized_payload_from_typed_message, publish_dual_control, publish_dual_supervisor_state
from inspection_utils.runtime_common import assert_typed_interfaces_available
from inspection_utils.runtime_common import qos_profile
from inspection_utils.transport_common import CONTROL_TOPIC_TYPED, DIAGNOSTICS_TOPIC_TYPED, SUPERVISOR_COMMAND_TOPIC_TYPED, SUPERVISOR_STATE_TOPIC_TYPED, supervisor_command_payload_from_message
from inspection_utils.runtime_event_contracts import BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED, BRIDGE_HEARTBEAT_TOPIC_TYPED, DECISION_PUBLISHED_TOPIC_TYPED, FAULT_RAISED_TOPIC_TYPED, FSM_TRANSITION_TOPIC_TYPED, RuntimeEventDeduper, VISION_FRAME_ACQUIRED_TOPIC_TYPED, is_runtime_event_payload, normalize_runtime_event_message
from inspection_utils.lifecycle_common import normalize_governed_node_name
from .lifecycle_graph import DEFAULT_LIFECYCLE_GRAPH_PATH, load_lifecycle_graph, load_runtime_topology, monitored_topology, ordered_monitored_startup, ordered_startup
from .lifecycle_manager import LifecycleManager
from .mode_manager import ModeManager, SupervisorMode
from .native_lifecycle_probe import NativeLifecycleProbe
from .native_lifecycle_dispatcher import NativeLifecycleDispatcher
from .node_health_registry import NodeHealthRegistry
from .recovery_policy import build_recovery_plan
from .startup_policy import startup_actions


class SupervisorNode(ExternalServiceRuntimeMixin, StandardRuntimeNode):
    def __init__(self) -> None:
        super().__init__('inspection_supervisor_node')
        self.declare_parameter('health_timeout_sec', 3.0)
        self.declare_parameter('lifecycle_graph_path', DEFAULT_LIFECYCLE_GRAPH_PATH)
        lifecycle_graph_path = str(self.get_parameter('lifecycle_graph_path').value or DEFAULT_LIFECYCLE_GRAPH_PATH)
        runtime_topology = load_runtime_topology(lifecycle_graph_path)
        lifecycle_graph = load_lifecycle_graph(lifecycle_graph_path)
        monitored_graph = monitored_topology(lifecycle_graph_path)
        startup_order = ordered_startup(lifecycle_graph)
        monitored_startup_order = ordered_monitored_startup(runtime_topology)
        self.declare_parameter('expected_nodes', monitored_startup_order)
        self.declare_parameter('required_nodes', [spec.name for spec in monitored_graph if spec.required])
        self.declare_parameter('profile_name', 'production')
        self.declare_parameter('autostart_mode', 'AUTO')
        expected = [str(v) for v in self.get_parameter('expected_nodes').value]
        required = {str(v) for v in self.get_parameter('required_nodes').value}
        node_classes = {spec.name: spec.criticality for spec in monitored_graph}
        node_domains = {spec.name: spec.fault_domain for spec in monitored_graph}
        self.runtime_topology = runtime_topology
        self.lifecycle_graph = lifecycle_graph
        self.monitored_graph = monitored_graph
        self.monitored_startup_order = monitored_startup_order
        self.registry = NodeHealthRegistry(expected_nodes=expected, required_nodes=required, node_classes=node_classes, node_domains=node_domains)
        self.lifecycle_manager = LifecycleManager(ordered_nodes=startup_order)
        self.mode_manager = ModeManager()
        self.mode_manager.request(str(self.get_parameter('autostart_mode').value), reason='startup')
        self.profile_name = str(self.get_parameter('profile_name').value)
        self.last_diagnostics: dict[str, object] = {}
        self.runtime_event_deduper = RuntimeEventDeduper(max_entries=512, ttl_sec=2.0)
        self.rejected_supervisor_commands = 0
        self.state_pub = self.create_publisher(String, '/inspection/supervisor/state', qos_profile('event'))
        self.typed_state_pub = self.create_publisher(SupervisorStateEnvelope, SUPERVISOR_STATE_TOPIC_TYPED, qos_profile('event')) if SupervisorStateEnvelope is not None else None
        self.control_pub = self.create_publisher(String, '/inspection/control', qos_profile('control'))
        self.typed_control_pub = self.create_publisher(ControlCommand, CONTROL_TOPIC_TYPED, qos_profile('control')) if ControlCommand is not None else None
        self.lifecycle_pub = self.create_publisher(String, '/inspection/lifecycle/command', qos_profile('control'))
        self.event_pub = self.create_publisher(String, '/inspection/events', qos_profile('event'))
        self.event_sub = self.create_subscription(String, '/inspection/events', self.on_event, qos_profile('event'))
        self.typed_fsm_transition_sub = self.create_subscription(FsmTransitionEvent, FSM_TRANSITION_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if FsmTransitionEvent is not None else None
        self.typed_vision_frame_sub = self.create_subscription(VisionFrameAcquiredEvent, VISION_FRAME_ACQUIRED_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if VisionFrameAcquiredEvent is not None else None
        self.typed_decision_sub = self.create_subscription(DecisionPublishedEvent, DECISION_PUBLISHED_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if DecisionPublishedEvent is not None else None
        self.typed_bridge_heartbeat_sub = self.create_subscription(BridgeHeartbeatEvent, BRIDGE_HEARTBEAT_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if BridgeHeartbeatEvent is not None else None
        self.typed_bridge_handshake_sub = self.create_subscription(BridgeHandshakeCompleteEvent, BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if BridgeHandshakeCompleteEvent is not None else None
        self.typed_fault_raised_sub = self.create_subscription(FaultRaisedEvent, FAULT_RAISED_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if FaultRaisedEvent is not None else None
        self.diagnostics_sub = self.create_subscription(String, '/inspection/diagnostics', self.on_diagnostics, qos_profile('diagnostics'))
        self.typed_diagnostics_sub = self.create_subscription(DiagnosticsSnapshot, DIAGNOSTICS_TOPIC_TYPED, self.on_typed_diagnostics, qos_profile('diagnostics')) if DiagnosticsSnapshot is not None else None
        self.control_sub = self.create_subscription(String, '/inspection/supervisor/command', self.on_command, qos_profile('control'))
        self.typed_control_sub = self.create_subscription(SupervisorCommand, SUPERVISOR_COMMAND_TOPIC_TYPED, self.on_typed_command, qos_profile('control')) if SupervisorCommand is not None else None
        self.lifecycle_dispatcher = NativeLifecycleDispatcher(self)
        self.lifecycle_probe = NativeLifecycleProbe(self, timeout_sec=0.05)
        self.timer = self.create_timer(0.5, self.publish_state)
        assert_typed_interfaces_available(consumer='inspection_supervisor_node', symbols={
            'ControlCommand': ControlCommand,
            'DiagnosticsSnapshot': DiagnosticsSnapshot,
            'SupervisorCommand': SupervisorCommand,
            'SupervisorStateEnvelope': SupervisorStateEnvelope,
            'BridgeHandshakeCompleteEvent': BridgeHandshakeCompleteEvent,
            'BridgeHeartbeatEvent': BridgeHeartbeatEvent,
            'DecisionPublishedEvent': DecisionPublishedEvent,
            'FaultRaisedEvent': FaultRaisedEvent,
            'FsmTransitionEvent': FsmTransitionEvent,
            'VisionFrameAcquiredEvent': VisionFrameAcquiredEvent,
        })
        self.setup_external_runtime(node_name='inspection_supervisor_node', initial_state='ACTIVE')

    def on_shutdown(self) -> tuple[bool, str]:
        """Mark the supervisor runtime finalized before process teardown.

        Returns:
            Tuple containing success flag and human-readable shutdown message.

        Boundary behavior:
            The supervisor intentionally stays outside lifecycle governance, so
            shutdown only mutates the local runtime-state guard used by
            diagnostics and ``publish_state``.
        """
        self.mark_external_runtime_state('FINALIZED')
        return True, 'supervisor shutdown'

    def _ingest_event_payload(self, payload: dict[str, object]) -> None:
        if is_runtime_event_payload(payload) and self.runtime_event_deduper.seen_recently(payload):
            return
        node = normalize_governed_node_name(str(payload.get('node', '')))
        if not node:
            return
        state = payload.get('state') or payload.get('phase') or payload.get('lifecycle_state')
        self.registry.ingest_event(node, now=time.monotonic(), event_type=str(payload.get('type', '')), state=str(state).upper() if state else None, detail=payload)

    def on_event(self, msg: String) -> None:
        self._ingest_event_payload(safe_json_loads(msg.data))

    def on_typed_event(self, msg: object) -> None:
        payload = safe_json_loads(getattr(msg, 'payload_json', '') or '{}', {})
        default_event_type = str(payload.get('type', '') or 'runtime_event')
        self._ingest_event_payload(normalize_runtime_event_message(msg, default_event_type=default_event_type))

    def on_diagnostics(self, msg: String) -> None:
        self.on_diagnostics_payload(safe_json_loads(msg.data))

    def on_diagnostics_payload(self, payload: dict[str, object]) -> None:
        self.last_diagnostics = payload
        source = str(self.last_diagnostics.get('node', 'inspection_diagnostics_node'))
        self.registry.ingest_event(source, now=time.monotonic(), event_type='diagnostics_update', state='ACTIVE', detail=self.last_diagnostics)

    def on_typed_diagnostics(self, msg: object) -> None:
        self.on_diagnostics_payload(normalized_payload_from_typed_message(msg, default_event_type='diagnostics_snapshot', bridge_name='diagnostics'))

    def on_typed_command(self, msg: object) -> None:
        """Bridge typed supervisor commands onto the legacy processing path.

        Args:
            msg: Typed ``SupervisorCommand`` ROS message.

        Returns:
            None. The method delegates to :meth:`on_command` after canonical
            normalization.

        Raises:
            No exception is intentionally propagated. Malformed typed messages are
            converted into diagnostics and audit events so the supervisor loop
            stays healthy without silently swallowing control-plane failures.

        Boundary behavior:
            During migration the supervisor accepts both legacy JSON and typed
            command topics, but both paths share the same downstream mode-change
            logic.
        """
        try:
            payload = supervisor_command_payload_from_message(msg, default_event_type='supervisor_command')
        except Exception as exc:
            self.rejected_supervisor_commands += 1
            detail = {
                'reason': 'typed_supervisor_command_invalid',
                'error': str(exc) or exc.__class__.__name__,
                'schema_version': str(getattr(msg, 'schema_version', 'v1') or 'v1'),
                'source': str(getattr(msg, 'source', '') or ''),
                'command': str(getattr(msg, 'command', '') or ''),
                'target_mode': str(getattr(msg, 'target_mode', '') or ''),
                'rejectedSupervisorCommands': self.rejected_supervisor_commands,
            }
            self.get_logger().warning('Rejected malformed typed supervisor command: %s', detail)
            self._emit_supervisor_command_rejected(detail)
            return
        self.on_command_payload(payload)

    def on_command(self, msg: String) -> None:
        """Handle external supervisor commands and bridge them to FSM controls.

        Args:
            msg: JSON-encoded supervisor command envelope published by gateway or
                other control-plane callers.

        Returns:
            None. Side effects are limited to supervisor mode mutation and
            downstream control-topic publications.

        Raises:
            No exception is propagated. Invalid payloads or request failures are
            converted into ignored commands so the supervisor spin loop remains
            healthy.

        Boundary behavior:
            Leaving maintenance mode now emits ``EXIT_MANUAL`` before any target
            automation command so manual-state guards cannot remain latched.
        """
        self.on_command_payload(safe_json_loads(msg.data))

    def on_command_payload(self, payload: dict[str, object]) -> None:
        command = str(payload.get('command', '')).lower()
        if command != 'set_mode':
            return
        target_mode = str(payload.get('mode', '')).upper()
        previous_mode = self.mode_manager.current_mode.value
        try:
            changed = self.mode_manager.request(target_mode, reason=str(payload.get('reason', 'external_command')))
        except Exception:
            changed = False
        if not changed:
            return
        if previous_mode == SupervisorMode.MAINTENANCE.value and target_mode != SupervisorMode.MAINTENANCE.value:
            self._publish_control(EXIT_MANUAL_COMMAND, reason='leave_maintenance_mode')
        if target_mode == SupervisorMode.AUTO.value:
            self._publish_control(RESUME_COMMAND)
        elif target_mode == SupervisorMode.PAUSED.value:
            self._publish_control(PAUSE_COMMAND)
        elif target_mode == SupervisorMode.MAINTENANCE.value:
            self._publish_control(ENTER_MANUAL_COMMAND)
        elif target_mode == SupervisorMode.STOPPED.value:
            self._publish_control(STOP_COMMAND)

    def _publish_control(self, command: str, **extra: object) -> None:
        """Publish a canonical control command to the station control plane.

        Args:
            command: Requested control command string.
            **extra: Additional diagnostic fields included in the outbound event envelope.
        """
        normalized_command = normalize_control_command(command)
        publish_dual_control(
            legacy_publisher=self.control_pub,
            typed_publisher=self.typed_control_pub,
            typed_message_cls=ControlCommand,
            command=normalized_command,
            source='inspection_supervisor_node',
            event_type='supervisor_control',
            reason=str(extra.get('reason', '')),
            batch_id=str(extra.get('batch_id', '')),
            item_id=int(extra.get('item_id', -1) or -1),
            trace_id=str(extra.get('trace_id', '')),
            extra=extra,
        )

    def _publish_lifecycle_command(self, payload: dict[str, object]) -> None:
        lifecycle_msg = String()
        lifecycle_msg.data = event_to_json('lifecycle_command', source='inspection_supervisor_node', **payload)
        self.lifecycle_pub.publish(lifecycle_msg)

    def _emit_supervisor_command_rejected(self, detail: dict[str, object]) -> None:
        """Publish one audit-friendly event for malformed supervisor commands.

        Args:
            detail: Structured rejection detail.

        Returns:
            None.

        Raises:
            No exception is propagated. Event publication best-effort only.

        Boundary behavior:
            Rejections are emitted on the shared inspection event bus so gateway
            diagnostics and recordings can trace malformed control-plane input
            without interrupting the supervisor spin loop.
        """
        event = String()
        event.data = event_to_json('supervisor_command_rejected', source='inspection_supervisor_node', **detail)
        self.event_pub.publish(event)

    def publish_state(self) -> None:
        if self.lifecycle_state == 'FINALIZED':
            return
        timeout = float(self.get_parameter('health_timeout_sec').value)
        now = time.monotonic()
        lifecycle = self.lifecycle_manager.evaluate(self.registry, now=now, timeout_sec=timeout, mode=self.mode_manager.current_mode.value)
        health = lifecycle['health']
        startup = startup_actions(self.registry, list(self.monitored_startup_order))
        recovery = build_recovery_plan(
            healthy=bool(health.get('healthy', False)),
            stale_nodes=list(health.get('stale_nodes', [])),
            missing_active_nodes=list(health.get('missing_active_nodes', [])),
            current_mode=self.mode_manager.current_mode.value,
            fault_domains=health.get('faultDomains', {}),
        )
        next_lifecycle_command = lifecycle.get('next_lifecycle_command', {})
        state = {
            'node': 'inspection_supervisor_node',
            'type': 'supervisor_state',
            'profile_name': self.profile_name,
            'mode': self.mode_manager.snapshot(),
            'health': health,
            'startup_actions': startup,
            'lifecycle_plan': lifecycle['lifecycle_plan'],
            'next_lifecycle_command': next_lifecycle_command,
            'lifecycle_executor': lifecycle.get('executor', {}),
            'recovery_plan': recovery,
            'diagnostics': self.last_diagnostics,
            'rejected_supervisor_commands': self.rejected_supervisor_commands,
            'native_lifecycle_observation': {
                'available': self.lifecycle_probe.availability().__dict__,
                'nodes': self.lifecycle_probe.describe_nodes(self.lifecycle_manager.ordered_nodes) if self.lifecycle_probe.enabled else {},
            },
            'runtime_topology': {
                'lifecycleManagedNodes': ordered_startup(self.lifecycle_graph),
                'supervisorMonitoredNodes': list(self.monitored_startup_order),
                'faultDomains': sorted({spec.fault_domain for spec in self.monitored_graph}),
                'externalServiceNodes': [spec.name for spec in self.runtime_topology if not spec.lifecycle_managed and not spec.supervisor_monitored],
            },
        }
        publish_dual_supervisor_state(
            legacy_publisher=self.state_pub,
            typed_publisher=self.typed_state_pub,
            typed_message_cls=SupervisorStateEnvelope,
            node_name='inspection_supervisor_node',
            profile_name=self.profile_name,
            current_mode=self.mode_manager.current_mode.value,
            payload=state,
            event_type='supervisor_state',
        )
        if next_lifecycle_command:
            dispatch_result = self.lifecycle_dispatcher.dispatch(
                self.lifecycle_manager.resolve_command(next_lifecycle_command),
                fallback=self._publish_lifecycle_command,
            )
            if dispatch_result.get('queued', False):
                self.lifecycle_manager.mark_dispatched(next_lifecycle_command)
            self.registry.ingest_event(
                'inspection_supervisor_node',
                now=time.monotonic(),
                event_type='lifecycle_dispatch',
                state='ACTIVE',
                detail={'type': 'lifecycle_dispatch', 'dispatch': dispatch_result, 'dispatched': bool(dispatch_result.get('queued', False)), **next_lifecycle_command},
            )
        if not health['healthy'] and self.mode_manager.current_mode == SupervisorMode.AUTO:
            reason = 'critical_health_degraded' if health.get('critical_stale_nodes') or health.get('critical_missing_nodes') else 'health_degraded'
            self._publish_control(PAUSE_COMMAND, reason=reason)


def main() -> None:
    rclpy.init()
    node = SupervisorNode()
    try:
        rclpy.spin(node)
    finally:
        node.on_shutdown()
        node.destroy_node()
        rclpy.shutdown()
