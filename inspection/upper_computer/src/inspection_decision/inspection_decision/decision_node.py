from __future__ import annotations

import json

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import DecisionPublishedEvent, InspectionResult, SortCommand
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    DecisionPublishedEvent = None
    from inspection_interfaces.msg import InspectionResult, SortCommand
from inspection_utils.config_common import build_effective_runtime_bundle
from inspection_utils.logging_common import event_to_json, safe_json_loads
from inspection_utils.runtime_common import ManagedNodeMixin
from inspection_utils.runtime_common import qos_profile
from inspection_utils.runtime_common import InspectionRuntimeNode
from inspection_utils.runtime_event_contracts import DECISION_PUBLISHED_TOPIC_TYPED, populate_decision_published_message, publish_dual_runtime_event
from inspection_utils.station_common import DECISION_OUTPUT_TOPIC
from .arbitration_engine import ArbitrationEngine
from .policy_engine import apply_policy_overrides
from .rules import decide_with_trace


class DecisionNode(ManagedNodeMixin, InspectionRuntimeNode):
    """Decision node that maps validated inspection results to decision outputs.

    The node only publishes the business decision product. Device execution is
    delegated to the FSM, which transforms a buffered decision into a station
    sort request once the control-state guards allow dispatch.
    """

    def __init__(self) -> None:
        super().__init__('decision_node')
        self.declare_parameter('recipe_path', 'config/recipes/default_recipe.yaml')
        self.declare_parameter('camera_config_path', 'config/camera/camera.yaml')
        self.declare_parameter('station_config_path', 'config/station/station.yaml')
        self.declare_parameter('profile_name', 'production')
        self.declare_parameter('profile_config_path', '')
        self.declare_parameter('compatibility_path', 'config/compatibility/matrix.yaml')

        profile_config_raw = str(self.get_parameter('profile_config_path').value or '').strip()
        effective_bundle = build_effective_runtime_bundle(
            recipe_path=str(self.get_parameter('recipe_path').value),
            camera_config_path=str(self.get_parameter('camera_config_path').value),
            station_config_path=str(self.get_parameter('station_config_path').value),
            profile_name=str(self.get_parameter('profile_name').value),
            profile_config_path=profile_config_raw or None,
            compatibility_path=str(self.get_parameter('compatibility_path').value),
            resource_package_name='inspection_bringup',
            resource_start=__file__,
        )
        self.recipe = effective_bundle['recipe']
        self.arbitration = ArbitrationEngine(self.recipe)
        self.pub = self.create_publisher(SortCommand, DECISION_OUTPUT_TOPIC, qos_profile('result'))
        self.event_pub = self.create_publisher(String, '/inspection/events', qos_profile('event'))
        self.typed_decision_pub = self.create_publisher(DecisionPublishedEvent, DECISION_PUBLISHED_TOPIC_TYPED, qos_profile('event')) if DecisionPublishedEvent is not None else None
        self.sub = self.create_subscription(InspectionResult, '/inspection/result', self.on_result, qos_profile('result'))
        self.setup_managed_runtime(node_name='decision_node')

    def _emit_event(self, event_type: str, **fields) -> None:
        payload_json = event_to_json(event_type, node='decision_node', **fields)
        if event_type == 'decision_published':
            publish_dual_runtime_event(
                event_type='decision_published',
                legacy_publisher=self.event_pub,
                typed_publisher=self.typed_decision_pub,
                typed_message_cls=DecisionPublishedEvent,
                populate_message=populate_decision_published_message,
                payload=safe_json_loads(payload_json),
            )
            return
        msg = String()
        msg.data = payload_json
        self.event_pub.publish(msg)

    def on_configure(self):
        return True, 'decision configured'

    def on_activate(self):
        return True, 'decision active'

    def on_deactivate(self):
        return True, 'decision inactive'

    def on_cleanup(self):
        return True, 'decision cleaned'

    def on_shutdown(self):
        return True, 'decision shutdown'

    def on_result(self, result: InspectionResult) -> None:
        if not self.is_active():
            return
        outcome = self.arbitration.apply(
            result,
            apply_policy_overrides(result, decide_with_trace(result, self.recipe), self.recipe),
        )
        cmd = SortCommand()
        cmd.stamp = self.get_clock().now().to_msg()
        cmd.batch_id = result.batch_id
        cmd.item_id = result.item_id
        cmd.target_bin = outcome.target_bin
        cmd.action_code = outcome.action_code
        cmd.decision = outcome.decision
        parsed_detail = safe_json_loads(result.detail_json or '{}')
        trace_id = str(parsed_detail.get('trace_id', ''))
        detail = {
            'reason': outcome.reason,
            'matched_rule_id': outcome.matched_rule_id,
            'matched_rule_priority': outcome.matched_rule_priority,
            'confidence': outcome.confidence,
            'explanation': outcome.explanation,
            'policy_notes': outcome.policy_notes,
            'arbitration_notes': outcome.arbitration_notes,
            'severity': outcome.severity,
            'trace_id': trace_id,
            'retry_index': 0,
        }
        cmd.reason = json.dumps(detail, ensure_ascii=False, sort_keys=True)
        self.pub.publish(cmd)
        self._emit_event(
            'decision_published',
            output_topic=DECISION_OUTPUT_TOPIC,
            item_id=result.item_id,
            batch_id=result.batch_id,
            trace_id=trace_id,
            decision=outcome.decision,
            action_code=outcome.action_code,
            target_bin=outcome.target_bin,
            matched_rule_id=outcome.matched_rule_id,
            matched_rule_priority=outcome.matched_rule_priority,
            confidence=outcome.confidence,
            severity=outcome.severity,
            arbitration_notes=outcome.arbitration_notes,
        )


def main() -> None:
    rclpy.init()
    node = DecisionNode()
    try:
        rclpy.spin(node)
    finally:
        node.on_shutdown()
        node.destroy_node()
        rclpy.shutdown()
