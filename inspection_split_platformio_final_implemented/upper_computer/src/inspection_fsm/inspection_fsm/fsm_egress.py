from __future__ import annotations

from typing import Any

from std_msgs.msg import String

from inspection_interfaces.msg import CaptureRequest
from inspection_utils.logging_tools import safe_json_loads
from inspection_utils.transport_adapters import publish_dual_capture_request


class FsmEgressPublisher:
    """Own ROS side-effect publication for the station FSM.

    The adapter isolates publisher-specific behavior from ``FSMNode`` so the node
    can act as a lifecycle/ROS shell while the egress policy stays unit-testable.
    """

    def __init__(self, node: Any) -> None:
        self.node = node

    def publish_feed_request(self) -> None:
        req = String()
        req.data = self.node._event_to_json(
            'feed_request',
            command='feed_one',
            item_id=self.node.data.item_id,
            batch_id=self.node.data.batch_id,
            trace_id=self.node.data.trace_id,
            cycle_index=self.node.data.cycle_index,
        )
        self.node.feed_pub.publish(req)
        self.node.runtime.current.artifacts.set('last_feed_request', safe_json_loads(req.data))
        self.node.emit_event('feed_request_published', command='feed_one')

    def publish_capture_request(self) -> None:
        payload_json = publish_dual_capture_request(
            legacy_publisher=self.node.capture_pub,
            typed_publisher=self.node.typed_capture_pub,
            typed_message_cls=CaptureRequest,
            trace_id=str(self.node.data.trace_id or ''),
            batch_id=str(self.node.data.batch_id or ''),
            item_id=int(self.node.data.item_id or -1),
            frame_index=int(self.node.data.cycle_index or -1),
            source='inspection_fsm_node',
            extra={'cycle_index': self.node.data.cycle_index},
        )
        self.node.runtime.current.artifacts.set('last_capture_request', safe_json_loads(payload_json))
        self.node.emit_event('capture_request_published')

    def publish_sort_request(self) -> None:
        if self.node.last_sort_cmd is None:
            self.node.emit_event('sort_request_skipped', reason='no_sort_command_buffered')
            return
        self.node.sort_pub.publish(self.node.last_sort_cmd)
        self.node.runtime.current.artifacts.set('last_sort_request', safe_json_loads(self.node.last_sort_cmd.reason or '{}', {}))
        self.node.emit_event(
            'sort_request_published',
            decision=self.node.last_sort_cmd.decision,
            action_code=self.node.last_sort_cmd.action_code,
            target_bin=self.node.last_sort_cmd.target_bin,
        )

    def publish_reset_request(self) -> None:
        req = String()
        req.data = self.node._event_to_json(
            'reset_request',
            batch_id=self.node.data.batch_id,
            trace_id=self.node.data.trace_id,
            fault_code=self.node.data.last_fault_code,
        )
        self.node.reset_pub.publish(req)
        self.node.emit_event('reset_request_published', fault_code=self.node.data.last_fault_code)
