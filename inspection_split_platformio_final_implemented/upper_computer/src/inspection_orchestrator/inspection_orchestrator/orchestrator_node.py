from __future__ import annotations

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import ControlCommand, DiagnosticsSnapshot, SupervisorStateEnvelope
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    ControlCommand = DiagnosticsSnapshot = SupervisorStateEnvelope = None

from inspection_utils.logging_tools import event_to_json, safe_json_loads
from inspection_utils.managed_node import ManagedNodeMixin
from inspection_utils.qos import qos_profile
from inspection_utils.param_parsing import parameter_as_bool
from inspection_utils.transport_contracts import CONTROL_TOPIC_TYPED, DIAGNOSTICS_TOPIC_TYPED, SUPERVISOR_STATE_TOPIC_TYPED
from inspection_utils.runtime_node import InspectionRuntimeNode
from inspection_utils.transport_adapters import legacy_payload_json_from_typed_message, publish_dual_control
from inspection_utils.typed_interfaces import assert_typed_interfaces_available
from .task_tree.auto_run_tree import evaluate_auto_run
from .task_tree.benchmark_tree import evaluate_benchmark
from .task_tree.maintenance_tree import evaluate_maintenance
from .task_tree.recovery_tree import evaluate_recovery
from .task_tree.startup_tree import evaluate_startup


class OrchestratorNode(ManagedNodeMixin, InspectionRuntimeNode):
    def __init__(self) -> None:
        super().__init__('inspection_orchestrator_node')
        self.declare_parameter('auto_recover', False)
        self.last_supervisor: dict[str, object] = {}
        self.last_diagnostics: dict[str, object] = {}
        self.state_sub = self.create_subscription(String, '/inspection/supervisor/state', self.on_supervisor, qos_profile('status'))
        self.typed_state_sub = self.create_subscription(SupervisorStateEnvelope, SUPERVISOR_STATE_TOPIC_TYPED, self.on_typed_supervisor, qos_profile('status')) if SupervisorStateEnvelope is not None else None
        self.diagnostics_sub = self.create_subscription(String, '/inspection/diagnostics', self.on_diagnostics, qos_profile('status'))
        self.typed_diagnostics_sub = self.create_subscription(DiagnosticsSnapshot, DIAGNOSTICS_TOPIC_TYPED, self.on_typed_diagnostics, qos_profile('status')) if DiagnosticsSnapshot is not None else None
        self.control_pub = self.create_publisher(String, '/inspection/control', qos_profile('control'))
        self.typed_control_pub = self.create_publisher(ControlCommand, CONTROL_TOPIC_TYPED, qos_profile('control')) if ControlCommand is not None else None
        self.advice_pub = self.create_publisher(String, '/inspection/orchestrator/advice', qos_profile('event'))
        self.timer = self.create_timer(0.5, self.tick)
        assert_typed_interfaces_available(consumer='inspection_orchestrator_node', symbols={
            'ControlCommand': ControlCommand,
            'DiagnosticsSnapshot': DiagnosticsSnapshot,
            'SupervisorStateEnvelope': SupervisorStateEnvelope,
        })
        self.setup_managed_runtime(node_name='inspection_orchestrator_node')

    def on_configure(self) -> tuple[bool, str]:
        return True, 'orchestrator configured'

    def on_activate(self) -> tuple[bool, str]:
        return True, 'orchestrator active'

    def on_deactivate(self) -> tuple[bool, str]:
        return True, 'orchestrator inactive'

    def on_cleanup(self) -> tuple[bool, str]:
        return True, 'orchestrator cleaned'

    def on_shutdown(self) -> tuple[bool, str]:
        return True, 'orchestrator shutdown'

    def on_supervisor(self, msg: String) -> None:
        self.last_supervisor = safe_json_loads(msg.data)

    def on_typed_supervisor(self, msg: object) -> None:
        legacy = String()
        legacy.data = legacy_payload_json_from_typed_message(msg, default_event_type='supervisor_state')
        self.on_supervisor(legacy)

    def on_diagnostics(self, msg: String) -> None:
        self.last_diagnostics = safe_json_loads(msg.data)

    def on_typed_diagnostics(self, msg: object) -> None:
        legacy = String()
        legacy.data = legacy_payload_json_from_typed_message(msg, default_event_type='diagnostics_snapshot')
        self.on_diagnostics(legacy)

    def publish_action(self, command: str, **extra: object) -> None:
        reason = str(extra.get('reason', ''))
        batch_id = str(extra.get('batch_id', ''))
        item_id = int(extra.get('item_id', -1) or -1)
        trace_id = str(extra.get('trace_id', ''))
        passthrough = {key: value for key, value in extra.items() if key not in {'reason', 'batch_id', 'item_id', 'trace_id'}}
        publish_dual_control(
            legacy_publisher=self.control_pub,
            typed_publisher=self.typed_control_pub,
            typed_message_cls=ControlCommand,
            command=command,
            event_type='orchestrator_command',
            source='inspection_orchestrator_node',
            reason=reason,
            batch_id=batch_id,
            item_id=item_id,
            trace_id=trace_id,
            extra=passthrough,
        )

    def publish_advice(self, actions: list[dict[str, object]], tree: str) -> None:
        msg = String()
        msg.data = event_to_json('orchestrator_advice', node='inspection_orchestrator_node', tree=tree, actions=actions)
        self.advice_pub.publish(msg)

    def tick(self) -> None:
        if not self.is_active() or not self.last_supervisor:
            return
        mode = str(self.last_supervisor.get('mode', {}).get('current_mode', 'STOPPED'))
        if mode == 'STOPPED':
            actions = evaluate_startup(self.last_supervisor)
            tree = 'startup'
        elif mode == 'AUTO':
            actions = evaluate_auto_run(self.last_supervisor, self.last_diagnostics)
            tree = 'auto_run'
        elif mode == 'BENCHMARK':
            actions = evaluate_benchmark(self.last_supervisor, self.last_diagnostics)
            tree = 'benchmark'
        elif mode == 'MAINTENANCE':
            actions = evaluate_maintenance(self.last_supervisor)
            tree = 'maintenance'
        else:
            actions = evaluate_recovery(self.last_supervisor)
            tree = 'recovery'
        self.publish_advice(actions, tree)
        if tree == 'auto_run' and parameter_as_bool(self, 'auto_recover', default=False):
            for action in actions:
                if action.get('action') in {'pause', 'resume', 'reset_fault', 'enter_manual'}:
                    self.publish_action(str(action['action']), reason=str(action.get('reason', tree)))


def main() -> None:
    rclpy.init()
    node = OrchestratorNode()
    try:
        rclpy.spin(node)
    finally:
        try:
            node.on_shutdown()
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()
