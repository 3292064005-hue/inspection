from __future__ import annotations

import json

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from inspection_interfaces.msg import CountStats, FaultEvent, InspectionResult, StationState


class HMINode(Node):
    def __init__(self) -> None:
        super().__init__('inspection_hmi_node')
        self.latest = {
            'state': 'BOOT',
            'count': {},
            'result': {},
            'fault': None,
            'trace_id': '',
            'last_event': {},
        }
        self.create_subscription(InspectionResult, '/inspection/result', self.on_result, 10)
        self.create_subscription(CountStats, '/station/count_stats', self.on_stats, 10)
        self.create_subscription(StationState, '/station/state', self.on_state, 10)
        self.create_subscription(FaultEvent, '/station/fault', self.on_fault, 10)
        self.create_subscription(String, '/inspection/events', self.on_event, 20)
        self.timer = self.create_timer(1.0, self.render_console)

    def on_result(self, msg: InspectionResult) -> None:
        try:
            detail = json.loads(msg.detail_json or '{}')
        except json.JSONDecodeError:
            detail = {}
        self.latest['trace_id'] = detail.get('trace_id', '')
        self.latest['result'] = {
            'item_id': msg.item_id,
            'color': msg.color_name,
            'qr_ok': msg.qr_ok,
            'defect_type': msg.defect_type,
            'warnings': detail.get('warnings', []),
        }

    def on_stats(self, msg: CountStats) -> None:
        self.latest['count'] = {'total': msg.total_count, 'ok': msg.ok_count, 'ng': msg.ng_count, 'recheck': msg.recheck_count, 'yield_rate': round(msg.yield_rate, 3), 'avg_cycle_time_sec': round(msg.avg_cycle_time_sec, 3)}

    def on_state(self, msg: StationState) -> None:
        self.latest['state'] = msg.state

    def on_fault(self, msg: FaultEvent) -> None:
        self.latest['fault'] = {'code': msg.fault_code, 'desc': msg.description}

    def on_event(self, msg: String) -> None:
        try:
            self.latest['last_event'] = json.loads(msg.data)
        except json.JSONDecodeError:
            self.latest['last_event'] = {'raw': msg.data}

    def render_console(self) -> None:
        self.get_logger().info(json.dumps(self.latest, ensure_ascii=False, sort_keys=True))


def main() -> None:
    rclpy.init()
    node = HMINode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
