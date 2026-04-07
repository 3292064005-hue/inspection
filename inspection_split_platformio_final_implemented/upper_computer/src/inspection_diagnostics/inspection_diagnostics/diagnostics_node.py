from __future__ import annotations

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import DiagnosticsSnapshot
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    DiagnosticsSnapshot = None

from inspection_interfaces.msg import StationState
from inspection_utils.logging_tools import event_to_json, safe_json_loads
from inspection_utils.managed_node import ManagedNodeMixin
from inspection_utils.runtime_node import InspectionRuntimeNode
from inspection_utils.transport_contracts import DIAGNOSTICS_TOPIC_TYPED, diagnostics_payload
from inspection_utils.typed_interfaces import assert_typed_interfaces_available
from inspection_utils.lifecycle_matrix import lifecycle_governance_matrix
from inspection_utils.qos import qos_policy_matrix, qos_profile, qos_summary
from .diagnostic_adapter import snapshot_to_statuses
from .diagnostics_aggregator import DiagnosticsAggregator


class DiagnosticsNode(ManagedNodeMixin, InspectionRuntimeNode):
    def __init__(self) -> None:
        super().__init__('inspection_diagnostics_node')
        self.aggregator = DiagnosticsAggregator()
        self.event_sub = self.create_subscription(String, '/inspection/events', self.on_event, qos_profile('event'))
        self.station_sub = self.create_subscription(StationState, '/station/state', self.on_station, qos_profile('station_state'))
        self.pub = self.create_publisher(String, '/inspection/diagnostics', qos_profile('diagnostics'))
        self.typed_pub = self.create_publisher(DiagnosticsSnapshot, DIAGNOSTICS_TOPIC_TYPED, qos_profile('diagnostics')) if DiagnosticsSnapshot is not None else None
        self.status_pub = self.create_publisher(String, '/inspection/diagnostics/statuses', qos_profile('diagnostics'))
        self.timer = self.create_timer(0.5, self.publish_snapshot)
        assert_typed_interfaces_available(consumer='inspection_diagnostics_node', symbols={'DiagnosticsSnapshot': DiagnosticsSnapshot})
        self.setup_managed_runtime(node_name='inspection_diagnostics_node')

    def on_configure(self):
        return True, 'diagnostics configured'

    def on_activate(self):
        return True, 'diagnostics active'

    def on_deactivate(self):
        return True, 'diagnostics inactive'

    def on_cleanup(self):
        return True, 'diagnostics cleaned'

    def on_shutdown(self):
        return True, 'diagnostics shutdown'

    def on_event(self, msg: String) -> None:
        self.aggregator.ingest_event(safe_json_loads(msg.data))

    def on_station(self, msg: StationState) -> None:
        detail = safe_json_loads(msg.detail)
        detail.setdefault('heartbeat_ok', detail.get('heartbeat_ok', msg.state != 'HEARTBEAT_LOST'))
        detail.setdefault('state', msg.state)
        self.aggregator.ingest_station_state(detail)

    def publish_snapshot(self) -> None:
        if not self.is_active():
            return
        payload = self.aggregator.build_snapshot()
        payload.setdefault('qos_profiles', qos_summary())
        payload.setdefault('qos_policy_matrix', qos_policy_matrix())
        payload.setdefault('lifecycle_governance', lifecycle_governance_matrix())
        payload.setdefault('lifecycle_state', self.lifecycle_state)
        msg = String()
        msg.data = event_to_json('diagnostics_snapshot', node='inspection_diagnostics_node', **payload)
        self.pub.publish(msg)
        if self.typed_pub is not None and DiagnosticsSnapshot is not None:
            typed_payload = diagnostics_payload('inspection_diagnostics_node', 'diagnostics_snapshot', self.lifecycle_state, payload)
            typed = DiagnosticsSnapshot()
            typed.node = 'inspection_diagnostics_node'
            typed.event_type = 'diagnostics_snapshot'
            typed.lifecycle_state = self.lifecycle_state
            typed.schema_version = str(typed_payload.get('schema_version', 'v1') or 'v1')
            typed.payload_json = msg.data
            self.typed_pub.publish(typed)
        status_msg = String()
        status_msg.data = event_to_json('diagnostics_statuses', node='inspection_diagnostics_node', statuses=snapshot_to_statuses(payload))
        self.status_pub.publish(status_msg)


def main() -> None:
    rclpy.init()
    node = DiagnosticsNode()
    try:
        rclpy.spin(node)
    finally:
        node.on_shutdown()
        node.destroy_node()
        rclpy.shutdown()
