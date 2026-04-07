from __future__ import annotations

import json

import rclpy
from std_msgs.msg import String

from inspection_interfaces.msg import FaultEvent, SortCommand, StationState
from inspection_utils.logging_tools import safe_json_loads
from inspection_utils.managed_node import ManagedNodeMixin
from inspection_utils.runtime_node import InspectionRuntimeNode
from inspection_utils.qos import qos_profile
from inspection_utils.param_parsing import parameter_as_bool
from .bridge_base import BridgeSignal
from .capability_registry import StationCapabilities
from .command_center import CommandCenter
from .mock_adapter import MockStationAdapter
from .reconnect_policy import ReconnectPolicy
from .reset_sync import ResetSync
from .serial_adapter import SerialStationAdapter
from .session_state import BridgeSession
from .watchdog import BridgeWatchdog
from .runtime_support import BridgeRuntimeSupport


class StationBridgeNode(ManagedNodeMixin, InspectionRuntimeNode):
    def __init__(self) -> None:
        super().__init__('station_bridge_node')
        self.declare_parameter('sim_mode', True)
        self.declare_parameter('serial_port', '/dev/ttyUSB0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('position_delay_sec', 0.3)
        self.declare_parameter('sort_delay_sec', 0.4)
        self.declare_parameter('heartbeat_sec', 1.0)
        self.declare_parameter('ack_stale_timeout_sec', 5.0)
        self.declare_parameter('heartbeat_watchdog_sec', 3.0)
        self.declare_parameter('enable_startup_handshake', True)
        self.sim_mode = parameter_as_bool(self, 'sim_mode', default=True)
        self.position_delay = float(self.get_parameter('position_delay_sec').value)
        self.sort_delay = float(self.get_parameter('sort_delay_sec').value)
        self.seq = 0
        self.batch_id = ''
        self.item_id = -1
        self.trace_id = ''
        self.capabilities = StationCapabilities(features={'SORT_ACK', 'HEARTBEAT'})
        self.command_center = CommandCenter()
        self.watchdog = BridgeWatchdog(float(self.get_parameter('heartbeat_watchdog_sec').value))
        self.handshake_done = False
        self.session = BridgeSession(protocol_version=1)
        self.reconnect_policy = ReconnectPolicy()
        self.reset_sync = ResetSync()
        self.next_reconnect_at = 0.0
        self.runtime_support = BridgeRuntimeSupport(self)
        self.state_pub = self.create_publisher(StationState, '/station/state', qos_profile('station_state'))
        self.event_pub = self.create_publisher(String, '/inspection/events', qos_profile('event'))
        self.fault_pub = self.create_publisher(FaultEvent, '/station/fault', qos_profile('diagnostics'))
        self.feed_sub = self.create_subscription(String, '/station/feed_request', self.on_feed_request, qos_profile('control'))
        self.sort_sub = self.create_subscription(SortCommand, '/station/sort_cmd', self.on_sort_cmd, qos_profile('result'))
        self.reset_sub = self.create_subscription(String, '/station/reset_request', self.on_reset_request, qos_profile('control'))
        hb = float(self.get_parameter('heartbeat_sec').value)
        self.create_timer(hb, self.publish_heartbeat)
        self.create_timer(0.05, self.poll_adapter)
        self.create_timer(0.25, self.check_stale_commands)
        self.create_timer(0.25, self.watchdog_tick)
        if self.sim_mode:
            self.adapter = MockStationAdapter(self.position_delay, self.sort_delay)
        else:
            self.adapter = SerialStationAdapter(
                port=str(self.get_parameter('serial_port').value),
                baudrate=int(self.get_parameter('baudrate').value),
            )
        self.adapter.set_callback(self.on_adapter_signal)
        if parameter_as_bool(self, 'enable_startup_handshake', default=True):
            self.start_handshake()
        self.setup_managed_runtime(node_name='station_bridge_node')

    def on_configure(self):
        return True, 'station bridge configured'

    def on_activate(self):
        return True, 'station bridge active'

    def on_deactivate(self):
        return True, 'station bridge inactive'

    def on_cleanup(self):
        return True, 'station bridge cleaned'

    def on_shutdown(self):
        self.runtime_support.close_adapter()
        return True, 'station bridge shutdown'

    def _next_seq(self) -> int:
        value = self.seq & 0xFF
        self.seq = (self.seq + 1) & 0xFF
        return value

    def _emit_event(self, event_type: str, **fields) -> None:
        self.runtime_support.emit_event(event_type, **fields)

    def _rollover_session(self, *, reason: str) -> None:
        self.runtime_support.rollover_session(reason=reason)

    def start_handshake(self) -> None:
        self.runtime_support.start_handshake()

    def publish_station(self, state_name: str, sensor: bool = False, gate_busy: bool = False, sorter_busy: bool = False, fault_code: str = '', detail: dict | None = None) -> None:
        self.runtime_support.publish_station(state_name, sensor=sensor, gate_busy=gate_busy, sorter_busy=sorter_busy, fault_code=fault_code, detail=detail)

    def publish_heartbeat(self) -> None:
        self.runtime_support.publish_heartbeat()

    def on_feed_request(self, msg: String) -> None:
        if not self.is_active():
            return
        request = safe_json_loads(msg.data)
        self.batch_id = str(request.get('batch_id', 'BATCH_DEMO'))
        self.item_id = int(request.get('item_id', self.item_id + 1))
        self.trace_id = str(request.get('trace_id', f'{self.batch_id}-{self.item_id:05d}'))
        seq = self._next_seq()
        self.command_center.register(seq, 'feed', self.trace_id, self.item_id, self.batch_id)
        self.publish_station('FEEDING', gate_busy=True, detail={'command': 'feed_one', 'seq': seq, 'generation': self.session.generation})
        self.adapter.send_feed(seq, json.dumps(request, ensure_ascii=False, sort_keys=True).encode('utf-8'))

    def on_sort_cmd(self, msg: SortCommand) -> None:
        if not self.is_active():
            return
        self.batch_id = msg.batch_id
        self.item_id = msg.item_id
        reason_data = safe_json_loads(msg.reason or '{}', {'reason': msg.reason})
        self.trace_id = str(reason_data.get('trace_id', self.trace_id or f'{self.batch_id}-{self.item_id:05d}'))
        seq = self._next_seq()
        retry_index = int(reason_data.get('retry_index', 0))
        self.command_center.register(seq, 'sort', self.trace_id, self.item_id, self.batch_id, retry_index=retry_index)
        detail = {
            'command': 'sort_to_bin',
            'decision': msg.decision,
            'action_code': msg.action_code,
            'target_bin': msg.target_bin,
            'seq': seq,
            'retry_index': retry_index,
            'generation': self.session.generation,
        }
        self.publish_station('SORTING', sorter_busy=True, detail=detail)
        payload = {
            'decision': msg.decision,
            'action_code': msg.action_code,
            'target_bin': msg.target_bin,
            'trace_id': self.trace_id,
            'item_id': self.item_id,
            'batch_id': self.batch_id,
            'session_generation': self.session.generation,
        }
        self.adapter.send_sort(seq, json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8'))

    def on_reset_request(self, msg: String) -> None:
        if self.lifecycle_state == 'FINALIZED':
            return
        payload = safe_json_loads(msg.data)
        self.trace_id = str(payload.get('trace_id', self.trace_id))
        seq = self._next_seq()
        self.command_center.register(seq, 'reset', self.trace_id, self.item_id, self.batch_id)
        self.reset_sync.start(seq)
        self.session.mark_resetting()
        self.adapter.reset_fault(seq, json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8'))
        self.publish_station('RESETTING', detail={'seq': seq, 'fault_code': payload.get('fault_code', ''), 'session_id': self.session.session_id, 'generation': self.session.generation})

    def _pending_or_orphan(self, signal: BridgeSignal, command_name: str, detail: dict) -> object | None:
        return self.runtime_support.pending_or_orphan(signal, command_name, detail)

    def on_adapter_signal(self, signal: BridgeSignal) -> None:
        self.runtime_support.handle_adapter_signal(signal)

    def publish_fault(self, code: str, detail: dict | None = None) -> None:
        self.runtime_support.publish_fault(code, detail)

    def poll_adapter(self) -> None:
        if self.lifecycle_state in {'UNCONFIGURED', 'FINALIZED'}:
            return
        self.adapter.poll()

    def check_stale_commands(self) -> None:
        self.runtime_support.check_stale_commands()

    def watchdog_tick(self) -> None:
        self.runtime_support.watchdog_tick()


def main() -> None:
    rclpy.init()
    node = StationBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.on_shutdown()
        node.destroy_node()
        rclpy.shutdown()
