from __future__ import annotations

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import ControlCommand, DiagnosticsSnapshot, SupervisorStateEnvelope
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    ControlCommand = DiagnosticsSnapshot = SupervisorStateEnvelope = None

from inspection_utils.logging_tools import event_to_json, safe_json_loads
from inspection_utils.managed_node import ManagedNodeMixin
from inspection_utils.param_parsing import parameter_as_bool
from inspection_utils.qos import qos_profile
from inspection_utils.runtime_node import InspectionRuntimeNode
from inspection_utils.transport_adapters import legacy_payload_json_from_typed_message, publish_dual_control
from inspection_utils.transport_contracts import CONTROL_TOPIC_TYPED, DIAGNOSTICS_TOPIC_TYPED, SUPERVISOR_STATE_TOPIC_TYPED
from inspection_utils.typed_interfaces import assert_typed_interfaces_available
from .task_tree.auto_run_tree import plan_auto_run
from .task_tree.benchmark_tree import plan_benchmark
from .task_tree.maintenance_tree import plan_maintenance
from .task_tree.recovery_tree import plan_recovery
from .task_tree.startup_tree import plan_startup
from .tree_runtime import OrchestratorPlanResult, OrchestratorTreeRuntime


class OrchestratorNode(ManagedNodeMixin, InspectionRuntimeNode):
    def __init__(self) -> None:
        super().__init__('inspection_orchestrator_node')
        self.declare_parameter('auto_recover', False)
        self.declare_parameter('execute_tree_modes', ['auto_run'])
        self.declare_parameter('executable_actions', ['pause', 'resume', 'reset_fault', 'enter_manual'])
        self.declare_parameter('tree_config_path', 'config/system/orchestrator_trees.yaml')
        self.declare_parameter('publish_tree_trace', True)
        self.last_supervisor: dict[str, object] = {}
        self.last_diagnostics: dict[str, object] = {}
        self.tree_runtime: OrchestratorTreeRuntime | None = None
        self.tree_config_error: str = ''
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

    def _load_tree_runtime(self) -> tuple[bool, str]:
        config_path = str(self.get_parameter('tree_config_path').value or 'config/system/orchestrator_trees.yaml')
        try:
            self.tree_runtime = OrchestratorTreeRuntime(config_path=config_path)
        except Exception as exc:
            self.tree_runtime = None
            self.tree_config_error = str(exc)
            return False, f'orchestrator tree config invalid: {exc}'
        self.tree_config_error = ''
        return True, f'orchestrator tree config loaded: {self.tree_runtime.config_path}'

    def on_configure(self) -> tuple[bool, str]:
        return self._load_tree_runtime()

    def on_activate(self) -> tuple[bool, str]:
        if self.tree_runtime is None:
            ok, message = self._load_tree_runtime()
            if not ok:
                return False, message
        return True, 'orchestrator active'

    def on_deactivate(self) -> tuple[bool, str]:
        return True, 'orchestrator inactive'

    def on_cleanup(self) -> tuple[bool, str]:
        self.tree_runtime = None
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

    def _configured_tree_modes(self) -> set[str]:
        value = self.get_parameter('execute_tree_modes').value
        if isinstance(value, (list, tuple, set)):
            return {str(item).strip() for item in value if str(item).strip()}
        return set()

    def _configured_executable_actions(self) -> set[str]:
        value = self.get_parameter('executable_actions').value
        if isinstance(value, (list, tuple, set)):
            return {str(item).strip() for item in value if str(item).strip()}
        return set()

    def _should_execute_tree(self, tree: str) -> bool:
        if tree == 'auto_run' and not parameter_as_bool(self, 'auto_recover', default=False):
            return False
        return tree in self._configured_tree_modes()

    def _execute_actions(self, *, result: OrchestratorPlanResult) -> None:
        if result.status != 'SUCCESS' or not self._should_execute_tree(result.tree):
            return
        allowed_actions = self._configured_executable_actions()
        for action in result.actions:
            action_name = str(action.get('action', '')).strip()
            if not action_name or action_name not in allowed_actions:
                continue
            self.publish_action(action_name, reason=str(action.get('reason', result.tree)))

    def publish_advice(self, result: OrchestratorPlanResult) -> None:
        msg = String()
        payload = {
            'node': 'inspection_orchestrator_node',
            'tree': result.tree,
            'status': result.status,
            'actions': result.actions,
            'durationMs': int(result.duration_ms),
        }
        if parameter_as_bool(self, 'publish_tree_trace', default=True):
            payload['trace'] = result.trace
        msg.data = event_to_json('orchestrator_advice', **payload)
        self.advice_pub.publish(msg)

    def _plan_for_mode(self, mode: str) -> OrchestratorPlanResult:
        if mode == 'STOPPED':
            return plan_startup(self.last_supervisor, runtime=self.tree_runtime)
        if mode == 'AUTO':
            return plan_auto_run(self.last_supervisor, self.last_diagnostics, runtime=self.tree_runtime)
        if mode == 'BENCHMARK':
            return plan_benchmark(self.last_supervisor, self.last_diagnostics, runtime=self.tree_runtime)
        if mode == 'MAINTENANCE':
            return plan_maintenance(self.last_supervisor, runtime=self.tree_runtime)
        return plan_recovery(self.last_supervisor, runtime=self.tree_runtime)

    def tick(self) -> None:
        if not self.is_active() or not self.last_supervisor:
            return
        if self.tree_runtime is None:
            ok, message = self._load_tree_runtime()
            if not ok:
                self.get_logger().error(message)
                return
        mode = str(self.last_supervisor.get('mode', {}).get('current_mode', 'STOPPED'))
        result = self._plan_for_mode(mode)
        self.publish_advice(result)
        self._execute_actions(result=result)


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
