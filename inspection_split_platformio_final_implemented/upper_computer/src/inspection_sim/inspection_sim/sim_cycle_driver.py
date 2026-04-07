from __future__ import annotations
import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class SimCycleDriver(Node):
    def __init__(self) -> None:
        super().__init__('sim_cycle_driver')
        self.pub = self.create_publisher(String, '/inspection/events', 10)
        self.timer = self.create_timer(2.0, self.on_timer)
        self.i = 0

    def on_timer(self) -> None:
        msg = String()
        msg.data = f'sim_driver_alive:{self.i}'
        self.pub.publish(msg)
        self.i += 1


def main() -> None:
    rclpy.init()
    node = SimCycleDriver()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
