from __future__ import annotations

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import BridgeHandshakeCompleteEvent, BridgeHeartbeatEvent, FaultEvent, SortCommand, StationState
except ImportError:  # pragma: no cover - ROS interface generation unavailable in unit-test environments
    BridgeHandshakeCompleteEvent = BridgeHeartbeatEvent = None
    from inspection_interfaces.msg import FaultEvent, SortCommand, StationState
from inspection_utils.runtime_common import ManagedNodeMixin
from inspection_utils.config_common import parameter_as_bool
from inspection_utils.runtime_common import qos_profile
from inspection_utils.runtime_common import InspectionRuntimeNode
from inspection_utils.runtime_event_contracts import BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED, BRIDGE_HEARTBEAT_TOPIC_TYPED
from inspection_utils.station_common import SORT_REQUEST_TOPIC
from inspection_utils.station_common import load_station_protocol_contract
from inspection_utils.station_common import load_station_capability_expectation, validate_station_capability_runtime_config

from .adapter_registry import adapter_manifest_catalog, build_station_adapter, canonical_protocol_version, normalize_adapter_name, resolve_protocol_version_number
from .bridge_base import BridgeSignal
from .capability_registry import StationCapabilities
from .command_center import CommandCenter
from .reconnect_policy import ReconnectPolicy
from .reset_sync import ResetSync
from .session_coordinator import BridgeSessionCoordinator
from .session_state import BridgeSession
from .watchdog import BridgeWatchdog


class StationBridgeNode(ManagedNodeMixin, InspectionRuntimeNode):
    """ROS shell for the station bridge protocol runtime.

    The node now consumes the declarative station runtime bundle instead of
    hardcoding adapter/protocol behavior inside the constructor.
    """

    def __init__(self) -> None:
        super().__init__('station_bridge_node')
        self.declare_parameter('sim_mode', True)
        self.declare_parameter('adapter_name', '')
        self.declare_parameter('protocol_version', 'v1')
        self.declare_parameter('supported_action_codes', [])
        self.declare_parameter('station_capability_profile', '')
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
        self.adapter_name = normalize_adapter_name(str(self.get_parameter('adapter_name').value), sim_mode=self.sim_mode)
        self.adapter_manifest_catalog = adapter_manifest_catalog()
        self.protocol_version_label = canonical_protocol_version(self.get_parameter('protocol_version').value or 'v1')
        self.protocol_contract = load_station_protocol_contract()
        configured_capability_profile = str(self.get_parameter('station_capability_profile').value or '').strip()
        self.station_capability_profile = configured_capability_profile or ('simulation_station_default' if self.sim_mode else 'stm32_station_default')
        self.station_capability_expectation = load_station_capability_expectation(self.station_capability_profile, start=__file__)
        configured_action_codes = self._parse_supported_action_codes(self.get_parameter('supported_action_codes').value)
        self.supported_action_codes = validate_station_capability_runtime_config(
            expectation=self.station_capability_expectation,
            adapter_name=self.adapter_name,
            protocol_version=self.protocol_version_label,
            supported_action_codes=configured_action_codes,
        )
        self.expected_station_features = set(self.station_capability_expectation.features)
        self.seq = 0
        self.batch_id = ''
        self.item_id = -1
        self.trace_id = ''
        self.capabilities = StationCapabilities(
            protocol_version=self.station_capability_expectation.protocol_version,
            firmware_version='configured-runtime',
            device_id=f'{self.adapter_name}-station',
            features=set(self.station_capability_expectation.features),
            supported_action_codes=tuple(sorted(self.supported_action_codes)),
        )
        self.command_center = CommandCenter()
        self.watchdog = BridgeWatchdog(float(self.get_parameter('heartbeat_watchdog_sec').value))
        self.handshake_done = False
        self.session = BridgeSession(protocol_version=resolve_protocol_version_number(self.protocol_version_label))
        self.reconnect_policy = ReconnectPolicy()
        self.reset_sync = ResetSync()
        self.next_reconnect_at = 0.0
        self.state_pub = self.create_publisher(StationState, '/station/state', qos_profile('station_state'))
        self.event_pub = self.create_publisher(String, '/inspection/events', qos_profile('event'))
        self.typed_bridge_heartbeat_pub = self.create_publisher(BridgeHeartbeatEvent, BRIDGE_HEARTBEAT_TOPIC_TYPED, qos_profile('event')) if BridgeHeartbeatEvent is not None else None
        self.typed_bridge_handshake_pub = self.create_publisher(BridgeHandshakeCompleteEvent, BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED, qos_profile('event')) if BridgeHandshakeCompleteEvent is not None else None
        self.fault_pub = self.create_publisher(FaultEvent, '/station/fault', qos_profile('diagnostics'))
        self.feed_sub = self.create_subscription(String, '/station/feed_request', self.on_feed_request, qos_profile('control'))
        self.sort_sub = self.create_subscription(SortCommand, SORT_REQUEST_TOPIC, self.on_sort_request, qos_profile('result'))
        self.reset_sub = self.create_subscription(String, '/station/reset_request', self.on_reset_request, qos_profile('control'))
        hb = float(self.get_parameter('heartbeat_sec').value)
        self.create_timer(hb, self.publish_heartbeat)
        self.create_timer(0.05, self.poll_adapter)
        self.create_timer(0.25, self.check_stale_commands)
        self.create_timer(0.25, self.watchdog_tick)
        self.adapter = build_station_adapter(
            adapter_name=self.adapter_name,
            position_delay_sec=self.position_delay,
            sort_delay_sec=self.sort_delay,
            serial_port=str(self.get_parameter('serial_port').value),
            baudrate=int(self.get_parameter('baudrate').value),
            capability_payload=self.station_capability_expectation.to_payload(
                firmware_version='mock-v5' if self.adapter_name == 'mock' else 'configured-runtime',
                device_id='mock-station' if self.adapter_name == 'mock' else f'{self.adapter_name}-station',
            ),
        )
        self.coordinator = BridgeSessionCoordinator(self)
        self.adapter.set_callback(self.on_adapter_signal)
        if parameter_as_bool(self, 'enable_startup_handshake', default=True):
            self.start_handshake()
        self.setup_managed_runtime(node_name='station_bridge_node')

    @staticmethod
    def _parse_supported_action_codes(raw_value: object) -> set[int]:
        """Normalize configured action codes into a deterministic integer set.

        Args:
            raw_value: Parameter payload supplied by ROS launch/runtime config.

        Returns:
            Parsed set of supported action codes.

        Raises:
            ValueError: When an entry cannot be interpreted as an integer.

        Boundary behavior:
            Empty or missing payloads produce an empty set, which means the
            bridge does not actively reject sort commands by action code.
        """
        if raw_value in (None, ''):
            return set()
        if not isinstance(raw_value, (list, tuple, set)):
            raise ValueError('supported_action_codes must be a list of integers')
        parsed: set[int] = set()
        for item in raw_value:
            parsed.add(int(item))
        return parsed

    def on_configure(self):
        return True, 'station bridge configured'

    def on_activate(self):
        return True, 'station bridge active'

    def on_deactivate(self):
        return True, 'station bridge inactive'

    def on_cleanup(self):
        return True, 'station bridge cleaned'

    def on_shutdown(self):
        self.coordinator.close_adapter()
        return True, 'station bridge shutdown'

    def _next_seq(self) -> int:
        value = self.seq & 0xFF
        self.seq = (self.seq + 1) & 0xFF
        return value

    def start_handshake(self) -> None:
        self.coordinator.start_handshake()

    def publish_station(self, state_name: str, sensor: bool = False, gate_busy: bool = False, sorter_busy: bool = False, fault_code: str = '', detail: dict | None = None) -> None:
        self.coordinator.publish_station(state_name, sensor=sensor, gate_busy=gate_busy, sorter_busy=sorter_busy, fault_code=fault_code, detail=detail)

    def publish_heartbeat(self) -> None:
        self.coordinator.publish_heartbeat()

    def on_feed_request(self, msg: String) -> None:
        self.coordinator.on_feed_request(msg.data)

    def on_sort_request(self, msg: SortCommand) -> None:
        """Submit one canonical station sort request to the adapter layer."""
        self.coordinator.on_sort_request(msg)

    def on_reset_request(self, msg: String) -> None:
        self.coordinator.on_reset_request(msg.data)

    def on_adapter_signal(self, signal: BridgeSignal) -> None:
        self.coordinator.handle_adapter_signal(signal)

    def publish_fault(self, code: str, detail: dict | None = None) -> None:
        self.coordinator.publish_fault(code, detail)

    def poll_adapter(self) -> None:
        self.coordinator.poll_adapter()

    def check_stale_commands(self) -> None:
        self.coordinator.check_stale_commands()

    def watchdog_tick(self) -> None:
        self.coordinator.watchdog_tick()


def main() -> None:
    rclpy.init()
    node = StationBridgeNode()
    try:
        rclpy.spin(node)
    finally:
        node.on_shutdown()
        node.destroy_node()
        rclpy.shutdown()
