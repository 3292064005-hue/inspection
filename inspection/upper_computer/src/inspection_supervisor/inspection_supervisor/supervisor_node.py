from __future__ import annotations

import time

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import ControlCommand, DiagnosticsSnapshot, SupervisorStateEnvelope
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    ControlCommand = DiagnosticsSnapshot = SupervisorStateEnvelope = None

from inspection_utils.control_protocol import (
    ENTER_MANUAL_COMMAND,
    PAUSE_COMMAND,
    EXIT_MANUAL_COMMAND,
    RESUME_COMMAND,
    STOP_COMMAND,
    normalize_control_command,
)
from inspection_utils.logging_tools import event_to_json, safe_json_loads
from inspection_utils.managed_node import ManagedNodeMixin
from inspection_utils.runtime_node import InspectionRuntimeNode
from inspection_utils.transport_adapters import legacy_payload_json_from_typed_message, publish_dual_control, publish_dual_supervisor_state
from inspection_utils.typed_interfaces import assert_typed_interfaces_available
from inspection_utils.qos import qos_profile
from inspection_utils.transport_contracts import CONTROL_TOPIC_TYPED, DIAGNOSTICS_TOPIC_TYPED, SUPERVISOR_STATE_TOPIC_TYPED
from inspection_utils.lifecycle_matrix import normalize_governed_node_name
from .lifecycle_graph import DEFAULT_LIFECYCLE_GRAPH, ordered_startup
from .lifecycle_manager import LifecycleManager
from .mode_manager import ModeManager, SupervisorMode
from .native_lifecycle_probe import NativeLifecycleProbe
from .native_lifecycle_dispatcher import NativeLifecycleDispatcher
from .node_health_registry import NodeHealthRegistry
from .recovery_policy import build_recovery_plan
from .startup_policy import startup_actions


class SupervisorNode(ManagedNodeMixin, InspectionRuntimeNode):
    def __init__(self) -> None:
        super().__init__('inspection_supervisor_node')
        self.declare_parameter('health_timeout_sec', 3.0)
        self.declare_parameter('expected_nodes', ordered_startup())
        self.declare_parameter('required_nodes', ordered_startup())
        self.declare_parameter('profile_name', 'production')
        self.declare_parameter('autostart_mode', 'AUTO')
        expected = [str(v) for v in self.get_parameter('expected_nodes').value]
        required = {str(v) for v in self.get_parameter('required_nodes').value}
        node_classes = {spec.name: ('critical' if spec.stage in {'core_io', 'control'} else ('required' if spec.required else 'optional')) for spec in DEFAULT_LIFECYCLE_GRAPH}
        self.registry = NodeHealthRegistry(expected_nodes=expected, required_nodes=required, node_classes=node_classes)
        self.lifecycle_manager = LifecycleManager(ordered_nodes=expected)
        self.mode_manager = ModeManager()
        self.mode_manager.request(str(self.get_parameter('autostart_mode').value), reason='startup')
        self.profile_name = str(self.get_parameter('profile_name').value)
        self.last_diagnostics: dict[str, object] = {}
        self.state_pub = self.create_publisher(String, '/inspection/supervisor/state', qos_profile('event'))
        self.typed_state_pub = self.create_publisher(SupervisorStateEnvelope, SUPERVISOR_STATE_TOPIC_TYPED, qos_profile('event')) if SupervisorStateEnvelope is not None else None
        self.control_pub = self.create_publisher(String, '/inspection/control', qos_profile('control'))
        self.typed_control_pub = self.create_publisher(ControlCommand, CONTROL_TOPIC_TYPED, qos_profile('control')) if ControlCommand is not None else None
        self.lifecycle_pub = self.create_publisher(String, '/inspection/lifecycle/command', qos_profile('control'))
        self.event_sub = self.create_subscription(String, '/inspection/events', self.on_event, qos_profile('event'))
        self.diagnostics_sub = self.create_subscription(String, '/inspection/diagnostics', self.on_diagnostics, qos_profile('diagnostics'))
        self.typed_diagnostics_sub = self.create_subscription(DiagnosticsSnapshot, DIAGNOSTICS_TOPIC_TYPED, self.on_typed_diagnostics, qos_profile('diagnostics')) if DiagnosticsSnapshot is not None else None
        self.control_sub = self.create_subscription(String, '/inspection/supervisor/command', self.on_command, qos_profile('control'))
        self.lifecycle_dispatcher = NativeLifecycleDispatcher(self)
        self.lifecycle_probe = NativeLifecycleProbe(self, timeout_sec=0.05)
        self.timer = self.create_timer(0.5, self.publish_state)
        assert_typed_interfaces_available(consumer='inspection_supervisor_node', symbols={
            'ControlCommand': ControlCommand,
            'DiagnosticsSnapshot': DiagnosticsSnapshot,
            'SupervisorStateEnvelope': SupervisorStateEnvelope,
        })
        self.setup_managed_runtime(node_name='inspection_supervisor_node')

    def on_configure(self):
        """Configure the supervisor managed runtime."""
        return True, 'supervisor configured'

    def on_activate(self):
        """Activate the supervisor managed runtime."""
        return True, 'supervisor active'

    def on_deactivate(self):
        """Deactivate the supervisor managed runtime."""
        return True, 'supervisor inactive'

    def on_cleanup(self):
        """Clean up supervisor managed runtime resources."""
        return True, 'supervisor cleaned'

    def on_shutdown(self):
        """Shut down the supervisor managed runtime."""
        return True, 'supervisor shutdown'

    def on_event(self, msg: String) -> None:
        payload = safe_json_loads(msg.data)
        node = normalize_governed_node_name(str(payload.get('node', '')))
        if not node:
            return
        state = payload.get('state') or payload.get('phase') or payload.get('lifecycle_state')
        self.registry.ingest_event(node, now=time.monotonic(), event_type=str(payload.get('type', '')), state=str(state).upper() if state else None, detail=payload)

    def on_diagnostics(self, msg: String) -> None:
        self.last_diagnostics = safe_json_loads(msg.data)
        source = str(self.last_diagnostics.get('node', 'inspection_diagnostics_node'))
        self.registry.ingest_event(source, now=time.monotonic(), event_type='diagnostics_update', state='ACTIVE', detail=self.last_diagnostics)

    def on_typed_diagnostics(self, msg: object) -> None:
        legacy = String()
        legacy.data = legacy_payload_json_from_typed_message(msg, default_event_type='diagnostics_snapshot')
        self.on_diagnostics(legacy)

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
        payload = safe_json_loads(msg.data)
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

    def publish_state(self) -> None:
        if self.lifecycle_state == 'FINALIZED':
            return
        timeout = float(self.get_parameter('health_timeout_sec').value)
        now = time.monotonic()
        lifecycle = self.lifecycle_manager.evaluate(self.registry, now=now, timeout_sec=timeout, mode=self.mode_manager.current_mode.value)
        health = lifecycle['health']
        startup = startup_actions(self.registry, ordered_startup())
        recovery = build_recovery_plan(
            healthy=bool(health.get('healthy', False)),
            stale_nodes=list(health.get('stale_nodes', [])),
            missing_active_nodes=list(health.get('missing_active_nodes', [])),
            current_mode=self.mode_manager.current_mode.value,
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
            'native_lifecycle_observation': {
                'available': self.lifecycle_probe.availability().__dict__,
                'nodes': self.lifecycle_probe.describe_nodes(self.lifecycle_manager.ordered_nodes) if self.lifecycle_probe.enabled else {},
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
