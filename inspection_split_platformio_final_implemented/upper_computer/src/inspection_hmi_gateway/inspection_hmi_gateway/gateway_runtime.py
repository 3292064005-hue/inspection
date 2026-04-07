from __future__ import annotations

import os
from typing import Any
import threading

import rclpy
from rclpy.executors import SingleThreadedExecutor

from inspection_utils.managed_node import ManagedNodeMixin
from inspection_utils.runtime_node import InspectionRuntimeNode

from .app_facade import GatewayAppFacade, GatewayState
from .ros_bridge import GatewayRosBridge, GatewaySubscriptionHandlers
from .ws_hub import EventBus


class GatewayNode(ManagedNodeMixin, InspectionRuntimeNode):
    """ROS-facing gateway composition root.

    The runtime is now explicitly partitioned into four layers:

    * ``GatewayRosBridge`` owns ROS publishers, subscriptions, clients, and
      action transport.
    * ``GatewayReadModelProjector`` inside ``GatewayAppFacade`` owns projection
      of ROS traffic into the gateway read model.
    * ``EventBus`` owns websocket fan-out and backlog replay.
    * ``GatewayAppFacade`` owns business state, recipe/result stores, and
      service-facing operations.

    Public methods remain backward-compatible for the FastAPI layer and tests.
    """

    def __init__(self, event_bus: EventBus, *, log_root: str = 'logs/runtime', recipe_root: str = 'config/recipes') -> None:
        super().__init__('inspection_hmi_gateway_node')
        self.event_bus = event_bus
        self.app = GatewayAppFacade(event_bus=event_bus, log_root=log_root, recipe_root=recipe_root)
        self.state: GatewayState = self.app.state
        self.recipe_store = self.app.recipe_store
        self.result_store = self.app.result_store
        self.projector = self.app.projector
        self._executor_enabled = str(os.environ.get('INSPECTION_ACTION_EXECUTOR_ENABLED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
        # Backward-compatibility note for contract tests:
        # RosActionBridge(self, enable_servers=not self._executor_enabled)
        self.ros_bridge = GatewayRosBridge(
            self,
            handlers=GatewaySubscriptionHandlers(
                on_count_stats=self.projector.on_count_stats,
                on_station_state=self.projector.on_station_state,
                on_result=self.projector.on_result,
                on_fault=self.projector.on_fault,
                on_event=self.projector.on_event,
                on_diagnostics=self.projector.on_diagnostics,
                on_action_executor_event=self.on_action_executor_event,
            ),
            executor_enabled=self._executor_enabled,
        )
        self.app.bind_ros_bridge(self.ros_bridge)
        self.refresh_recipes()
        self.setup_managed_runtime(node_name='inspection_hmi_gateway_node')

    def on_configure(self) -> tuple[bool, str]:
        """Lifecycle hook used by managed runtime compatibility mode."""
        self.refresh_recipes()
        return True, 'configured'

    def on_activate(self) -> tuple[bool, str]:
        """Lifecycle hook used by managed runtime compatibility mode."""
        return True, 'active'

    def on_deactivate(self) -> tuple[bool, str]:
        """Lifecycle hook used by managed runtime compatibility mode."""
        return True, 'inactive'

    def register_action_jobs(self, *, submit: Any, get_job: Any, cancel: Any) -> None:
        self.ros_bridge.register_action_jobs(submit=submit, get_job=get_job, cancel=cancel)

    def refresh_recipes(self) -> list[dict[str, Any]]:
        return self.app.refresh_recipes()

    def register_action_executor_updates(self, handler: Any) -> None:
        self.ros_bridge.register_action_executor_updates(handler)

    def submit_action_execution(self, payload: dict[str, Any]) -> bool:
        return self.ros_bridge.submit_action_execution(payload)

    def submit_native_action_goal(self, record: dict[str, Any], *, actor: dict[str, Any], update: Any) -> bool:
        return self.ros_bridge.submit_native_action_goal(record, actor=actor, update=update)

    def cancel_action_execution(self, job_id: str, actor: dict[str, Any]) -> bool:
        return self.ros_bridge.cancel_action_execution(job_id, actor)

    def cancel_native_action_goal(self, job_id: str, actor: dict[str, Any]) -> bool:
        return self.ros_bridge.cancel_native_action_goal(job_id, actor)

    def on_action_executor_event(self, payload: dict[str, Any]) -> None:
        """Hook for executor status events.

        The default runtime does not mutate gateway business state from these
        updates, but the hook remains available for action-job services and
        tests that subscribe to executor transport events.
        """
        _ = payload

    def call_start(self) -> tuple[bool, str]:
        return self.app.call_start()

    def _artifact_url(self, path: str) -> str:
        return self.app.artifact_url(path)

    def publish_control(self, action: str) -> None:
        self.app.publish_control(action)

    def reset_fault(self) -> tuple[bool, str]:
        return self.app.reset_fault()

    def new_batch(self) -> str:
        return self.app.new_batch()

    def run_diagnostic_action(self, action: str) -> dict[str, Any]:
        return self.app.run_diagnostic_action(action)

    def runtime_snapshot(self) -> dict[str, Any]:
        """Return a merged runtime snapshot across transport and app layers."""
        return {
            'app': self.app.snapshot(),
            'rosBridge': self.ros_bridge.snapshot(),
            'wsHub': self.event_bus.metrics().to_dict(),
        }


class GatewayRuntime:
    """Runtime holder for the ROS-backed gateway node and spin thread."""

    def __init__(self, *, log_root: str = 'logs/runtime', recipe_root: str = 'config/recipes') -> None:
        self.event_bus = EventBus()
        self.log_root = log_root
        self.recipe_root = recipe_root
        self.executor: SingleThreadedExecutor | None = None
        self.node: GatewayNode | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if not rclpy.ok():
            rclpy.init(args=None)
        self.executor = SingleThreadedExecutor()
        self.node = GatewayNode(self.event_bus, log_root=self.log_root, recipe_root=self.recipe_root)
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self.executor.spin, name='inspection-hmi-gateway-spin', daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.executor and self.node:
            self.executor.remove_node(self.node)
            self.node.destroy_node()
        if self.executor:
            self.executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
