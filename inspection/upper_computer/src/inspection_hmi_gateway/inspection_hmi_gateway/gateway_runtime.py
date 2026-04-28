from __future__ import annotations

import os
import threading
from typing import Any

import rclpy
from rclpy.executors import SingleThreadedExecutor

from inspection_utils.runtime_common import ExternalServiceRuntimeMixin, StandardRuntimeNode

from .action_contract import EXECUTOR_EVENT_TOPIC
from .application_service import GatewayApplicationService
from .ros_bridge import GatewayRosBridge, GatewaySubscriptionHandlers
from .ws_hub import EventBus


class GatewayNode(ExternalServiceRuntimeMixin, StandardRuntimeNode):
    """ROS-facing gateway composition root.

    The runtime is partitioned into transport, projection, event fan-out, and
    application-service layers. The authoritative gateway business boundary is exposed through ``self.app``.
    """

    def __init__(self, event_bus: EventBus, *, log_root: str = 'logs/runtime', recipe_root: str = 'config/recipes') -> None:
        super().__init__('inspection_hmi_gateway_server')
        self.event_bus = event_bus
        self.app = GatewayApplicationService(event_bus=event_bus, log_root=log_root, recipe_root=recipe_root)
        self.state = self.app.state
        self.state_store = self.app.state_store
        self.recipe_store = self.app.recipe_store
        self.result_store = self.app.result_store
        self.projector = self.app.projector
        self.control_plane = self.app.control_plane
        self.query_plane = self.app.query_plane
        self.recipe_plane = self.app.recipe_plane
        self._executor_enabled = str(os.environ.get('INSPECTION_ACTION_EXECUTOR_ENABLED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
        self.ros_bridge = GatewayRosBridge(
            self,
            handlers=GatewaySubscriptionHandlers(
                on_count_stats=self.projector.on_count_stats,
                on_station_state=self.projector.on_station_state,
                on_result=self.projector.on_result,
                on_fault=self.projector.on_fault,
                on_event=self.projector.on_event,
                on_diagnostics=self.projector.on_diagnostics,
                on_supervisor_state=self.projector.on_supervisor_state,
                on_orchestrator_advice=self.projector.on_orchestrator_advice,
                on_action_executor_event=self.on_action_executor_event,
            ),
            executor_enabled=self._executor_enabled,
        )
        self.app.bind_ros_bridge(self.ros_bridge)
        self.refresh_recipes()
        self.setup_external_runtime(node_name='inspection_hmi_gateway_server', initial_state='ACTIVE')

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

    def request_maintenance_mode(self, enabled: bool, *, actor: str = 'anonymous') -> dict[str, Any]:
        return self.app.request_maintenance_mode(enabled, actor=actor)

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
        self.mode = 'embedded'

    def start(self) -> None:
        if self.node is not None:
            return
        if not rclpy.ok():
            rclpy.init(args=None)
        self.executor = SingleThreadedExecutor()
        self.node = GatewayNode(self.event_bus, log_root=self.log_root, recipe_root=self.recipe_root)
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self.executor.spin, name='inspection-hmi-gateway-spin', daemon=True)
        self.thread.start()

    def stop(self) -> None:
        node = self.node
        executor = self.executor
        thread = self.thread
        if executor and node:
            executor.remove_node(node)
            if hasattr(node, 'mark_external_runtime_state'):
                node.mark_external_runtime_state('FINALIZED')
            node.destroy_node()
        if executor:
            executor.shutdown()
        if rclpy.ok():
            rclpy.shutdown()
        if thread and thread.is_alive():
            thread.join(timeout=1.0)
        self.node = None
        self.executor = None
        self.thread = None

    def health(self) -> dict[str, Any]:
        """Return runtime health for API readiness probes.

        Args:
            None.

        Returns:
            A JSON-serializable runtime health payload.

        Raises:
            No exception is intentionally raised.

        Boundary behavior:
            The probe reports process/runtime liveness separately from action
            transport expectations so operators can distinguish "HTTP is alive"
            from "action execution plane is wired as expected".
        """
        thread_alive = bool(self.thread and self.thread.is_alive())
        node_ready = self.node is not None
        executor_ready = self.executor is not None
        ros_bridge = getattr(self.node, 'ros_bridge', None) if self.node is not None else None
        ros_bridge_snapshot = ros_bridge.snapshot() if ros_bridge is not None and hasattr(ros_bridge, 'snapshot') else {}
        subscriptions = ros_bridge_snapshot.get('subscriptionsBound', []) if isinstance(ros_bridge_snapshot, dict) else []
        received_executor_updates = int(ros_bridge_snapshot.get('receivedExecutorUpdates', 0)) if isinstance(ros_bridge_snapshot, dict) else 0
        action_executor_expected = str(os.environ.get('INSPECTION_ACTION_EXECUTOR_ENABLED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
        native_action_client_enabled = str(os.environ.get('INSPECTION_NATIVE_ACTION_CLIENT_ENABLED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
        local_runtime_enabled = str(os.environ.get('INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED', '')).strip().lower() in {'1', 'true', 'yes', 'on'}
        action_transport_mode = 'native_action' if native_action_client_enabled else ('executor_bridge' if action_executor_expected else ('local_runtime' if local_runtime_enabled else 'detached'))
        executor_update_channel_bound = EXECUTOR_EVENT_TOPIC in subscriptions
        transport_ready = bool(node_ready and executor_ready and thread_alive and ros_bridge is not None and (not action_executor_expected or executor_update_channel_bound))
        transport_observed = bool(transport_ready and (not action_executor_expected or received_executor_updates > 0))
        action_execution = {
            'transportMode': action_transport_mode,
            'actionExecutorExpected': action_executor_expected,
            'nativeActionClientEnabled': native_action_client_enabled,
            'localRuntimeEnabled': local_runtime_enabled,
            'rosBridgeBound': ros_bridge is not None,
            'executorUpdateChannelBound': executor_update_channel_bound,
            'receivedExecutorUpdates': received_executor_updates,
            'transportReady': transport_ready,
            'transportObserved': transport_observed,
            'rosBridge': ros_bridge_snapshot,
        }
        return {
            'mode': self.mode,
            'runtimeReady': bool(node_ready and executor_ready and thread_alive),
            'nodeReady': node_ready,
            'executorReady': executor_ready,
            'spinThreadAlive': thread_alive,
            'stateVersion': int(getattr(getattr(self.node, 'state_store', None), 'version', 0)),
            'actionExecution': action_execution,
        }
