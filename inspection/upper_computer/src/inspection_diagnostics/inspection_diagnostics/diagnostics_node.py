from __future__ import annotations

import rclpy
from sensor_msgs.msg import Image
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import (
        BridgeHandshakeCompleteEvent,
        BridgeHeartbeatEvent,
        DecisionPublishedEvent,
        DiagnosticsSnapshot,
        FaultRaisedEvent,
        FsmTransitionEvent,
        StationState,
        VisionFrameAcquiredEvent,
    )
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    BridgeHandshakeCompleteEvent = BridgeHeartbeatEvent = DecisionPublishedEvent = DiagnosticsSnapshot = FaultRaisedEvent = FsmTransitionEvent = VisionFrameAcquiredEvent = None
    from inspection_interfaces.msg import StationState
from inspection_utils.logging_common import event_to_json, safe_json_loads
from inspection_utils.runtime_common import ManagedNodeMixin
from inspection_utils.runtime_common import InspectionRuntimeNode
from inspection_utils.transport_common import DIAGNOSTICS_TOPIC_TYPED, diagnostics_payload
from inspection_utils.runtime_common import assert_typed_interfaces_available
from inspection_utils.runtime_event_contracts import BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED, BRIDGE_HEARTBEAT_TOPIC_TYPED, DECISION_PUBLISHED_TOPIC_TYPED, FAULT_RAISED_TOPIC_TYPED, FSM_TRANSITION_TOPIC_TYPED, RuntimeEventDeduper, VISION_FRAME_ACQUIRED_TOPIC_TYPED, is_runtime_event_payload, normalize_runtime_event_message
from inspection_utils.lifecycle_common import lifecycle_governance_matrix
from inspection_utils.runtime_common import qos_policy_matrix, qos_profile, qos_summary
from inspection_utils.config_common import parameter_as_bool
from .diagnostic_adapter import snapshot_to_statuses
from .diagnostics_aggregator import DiagnosticsAggregator


from .subscription_policy import diagnostics_subscription_policy


class DiagnosticsNode(ManagedNodeMixin, InspectionRuntimeNode):
    def __init__(self) -> None:
        super().__init__('inspection_diagnostics_node')
        self.declare_parameter('enable_annotated_image_diagnostics', False)
        self.aggregator = DiagnosticsAggregator()
        self.runtime_event_deduper = RuntimeEventDeduper(max_entries=512, ttl_sec=2.0)
        self.subscription_policy = diagnostics_subscription_policy(
            parameter_as_bool(self, 'enable_annotated_image_diagnostics', default=False)
        )
        self.aggregator.set_annotated_stream_enabled(self.subscription_policy['annotated_image'])
        self.event_sub = self.create_subscription(String, '/inspection/events', self.on_event, qos_profile('event'))
        self.typed_fsm_transition_sub = self.create_subscription(FsmTransitionEvent, FSM_TRANSITION_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if FsmTransitionEvent is not None else None
        self.typed_vision_frame_sub = self.create_subscription(VisionFrameAcquiredEvent, VISION_FRAME_ACQUIRED_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if VisionFrameAcquiredEvent is not None else None
        self.typed_decision_sub = self.create_subscription(DecisionPublishedEvent, DECISION_PUBLISHED_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if DecisionPublishedEvent is not None else None
        self.typed_bridge_heartbeat_sub = self.create_subscription(BridgeHeartbeatEvent, BRIDGE_HEARTBEAT_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if BridgeHeartbeatEvent is not None else None
        self.typed_bridge_handshake_sub = self.create_subscription(BridgeHandshakeCompleteEvent, BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if BridgeHandshakeCompleteEvent is not None else None
        self.typed_fault_raised_sub = self.create_subscription(FaultRaisedEvent, FAULT_RAISED_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if FaultRaisedEvent is not None else None
        self.station_sub = self.create_subscription(StationState, '/station/state', self.on_station, qos_profile('station_state'))
        self.camera_status_sub = self.create_subscription(String, '/inspection/camera/status', self.on_camera_status, qos_profile('diagnostics'))
        self.result_raw_sub = self.create_subscription(String, '/inspection/result_raw', self.on_result_raw, qos_profile('event'))
        self.annotated_image_sub = self.create_subscription(Image, '/inspection/image_annotated', self.on_image_annotated, qos_profile('sensor_data')) if self.subscription_policy['annotated_image'] else None
        self.pub = self.create_publisher(String, '/inspection/diagnostics', qos_profile('diagnostics'))
        self.typed_pub = self.create_publisher(DiagnosticsSnapshot, DIAGNOSTICS_TOPIC_TYPED, qos_profile('diagnostics')) if DiagnosticsSnapshot is not None else None
        self.status_pub = self.create_publisher(String, '/inspection/diagnostics/statuses', qos_profile('diagnostics'))
        self.timer = self.create_timer(0.5, self.publish_snapshot)
        assert_typed_interfaces_available(consumer='inspection_diagnostics_node', symbols={'BridgeHandshakeCompleteEvent': BridgeHandshakeCompleteEvent, 'BridgeHeartbeatEvent': BridgeHeartbeatEvent, 'DecisionPublishedEvent': DecisionPublishedEvent, 'DiagnosticsSnapshot': DiagnosticsSnapshot, 'FaultRaisedEvent': FaultRaisedEvent, 'FsmTransitionEvent': FsmTransitionEvent, 'VisionFrameAcquiredEvent': VisionFrameAcquiredEvent})
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
        payload = safe_json_loads(msg.data)
        if is_runtime_event_payload(payload) and self.runtime_event_deduper.seen_recently(payload):
            return
        self.aggregator.ingest_event(payload)

    def on_typed_event(self, msg: object) -> None:
        payload = safe_json_loads(getattr(msg, 'payload_json', '') or '{}', {})
        default_event_type = str(payload.get('type', '') or 'runtime_event')
        normalized = normalize_runtime_event_message(msg, default_event_type=default_event_type)
        if is_runtime_event_payload(normalized) and self.runtime_event_deduper.seen_recently(normalized):
            return
        self.aggregator.ingest_event(normalized)

    def on_station(self, msg: StationState) -> None:
        detail = safe_json_loads(msg.detail)
        detail.setdefault('heartbeat_ok', detail.get('heartbeat_ok', msg.state != 'HEARTBEAT_LOST'))
        detail.setdefault('state', msg.state)
        self.aggregator.ingest_station_state(detail)

    def on_camera_status(self, msg: String) -> None:
        """Consume camera health snapshots emitted by the acquisition node.

        Args:
            msg: JSON payload published on ``/inspection/camera/status``.

        Returns:
            None.

        Raises:
            No additional exception is raised beyond JSON normalization.

        Boundary behavior:
            Malformed payloads are normalized into best-effort dictionaries so
            diagnostics publishing remains resilient.
        """
        payload = safe_json_loads(msg.data, {'status': 'camera_status_parse_failed', 'raw': msg.data})
        if isinstance(payload, dict):
            self.aggregator.ingest_camera_status(payload)

    def on_result_raw(self, msg: String) -> None:
        """Consume structured raw-result diagnostics from vision processing.

        Args:
            msg: JSON payload published on ``/inspection/result_raw``.

        Returns:
            None.

        Raises:
            No additional exception is raised beyond JSON normalization.

        Boundary behavior:
            Missing or malformed fields are preserved as best-effort values so
            the diagnostics channel remains readable during parser regressions.
        """
        payload = safe_json_loads(msg.data, {'type': 'vision_result_raw_parse_failed', 'raw': msg.data})
        if isinstance(payload, dict):
            self.aggregator.ingest_result_raw(payload)

    def on_image_annotated(self, msg: Image) -> None:
        """Track the annotated-image stream as a diagnostics-only consumer.

        Args:
            msg: ROS image message published on ``/inspection/image_annotated``.

        Returns:
            None.

        Raises:
            No additional exception is raised.

        Boundary behavior:
            Only frame metadata is retained to avoid duplicating the image
            artifact pipeline inside diagnostics.
        """
        self.aggregator.ingest_annotated_frame(
            {
                'frameId': str(getattr(getattr(msg, 'header', None), 'frame_id', '') or ''),
                'height': int(getattr(msg, 'height', 0) or 0),
                'width': int(getattr(msg, 'width', 0) or 0),
                'encoding': str(getattr(msg, 'encoding', '') or ''),
                'step': int(getattr(msg, 'step', 0) or 0),
            }
        )

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
