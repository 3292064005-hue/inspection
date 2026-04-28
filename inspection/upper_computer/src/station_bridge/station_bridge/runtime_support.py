from __future__ import annotations

import json
import time
from typing import Any

from inspection_utils.logging_common import event_to_json, safe_json_loads
try:
    from std_msgs.msg import String
except ImportError:  # pragma: no cover - unit-test fallback without ROS message generation
    class String:  # type: ignore[override]
        def __init__(self) -> None:
            self.data = ''


try:
    from inspection_interfaces.msg import BridgeHandshakeCompleteEvent, BridgeHeartbeatEvent, FaultEvent, StationState
except ImportError:  # pragma: no cover - unit-test fallback without ROS message generation
    BridgeHandshakeCompleteEvent = BridgeHeartbeatEvent = None

    class FaultEvent:  # type: ignore[override]
        pass

    class StationState:  # type: ignore[override]
        pass

from .bridge_base import BridgeSignal
from .capability_registry import StationCapabilities
from inspection_utils.station_common import StationProtocolContractError, validate_capabilities_payload, validate_runtime_protocol_version
from inspection_utils.runtime_event_contracts import (
    populate_bridge_handshake_complete_message,
    populate_bridge_heartbeat_message,
    publish_dual_runtime_event,
)


class BridgeRuntimeSupport:
    """Encapsulate bridge-side publishing, signal handling, watchdog, and adapter cleanup.

    The helper intentionally operates on the existing ``StationBridgeNode`` instance instead of
    owning publishers or runtime state itself. This keeps the ROS-facing interface unchanged while
    moving protocol-side responsibilities out of the node shell.
    """

    def __init__(self, node: Any) -> None:
        self.node = node

    def close_adapter(self) -> tuple[bool, str]:
        """Attempt to close the active station adapter.

        Returns:
            ``(True, '')`` when the adapter closes cleanly, otherwise ``(False, error_message)``.

        Boundary behavior:
            Adapter shutdown failures are converted into an event and a degraded session state
            instead of propagating during ROS teardown.
        """
        adapter = getattr(self.node, 'adapter', None)
        if adapter is None:
            return True, ''
        try:
            adapter.close()
            return True, ''
        except Exception as exc:  # pragma: no cover - defensive shutdown path
            self.node.session.mark_degraded()
            self.emit_event('bridge_adapter_close_failed', error=str(exc))
            return False, str(exc)

    def emit_event(self, event_type: str, **fields) -> None:
        payload_json = event_to_json(
            event_type,
            node='station_bridge_node',
            item_id=self.node.item_id,
            batch_id=self.node.batch_id,
            trace_id=self.node.trace_id,
            session=self.node.session.snapshot(),
            **fields,
        )
        if event_type == 'bridge_heartbeat':
            publish_dual_runtime_event(
                event_type='bridge_heartbeat',
                legacy_publisher=self.node.event_pub,
                typed_publisher=getattr(self.node, 'typed_bridge_heartbeat_pub', None),
                typed_message_cls=BridgeHeartbeatEvent,
                populate_message=populate_bridge_heartbeat_message,
                payload=safe_json_loads(payload_json),
            )
            return
        if event_type == 'bridge_handshake_complete':
            publish_dual_runtime_event(
                event_type='bridge_handshake_complete',
                legacy_publisher=self.node.event_pub,
                typed_publisher=getattr(self.node, 'typed_bridge_handshake_pub', None),
                typed_message_cls=BridgeHandshakeCompleteEvent,
                populate_message=populate_bridge_handshake_complete_message,
                payload=safe_json_loads(payload_json),
            )
            return
        evt = String()
        evt.data = payload_json
        self.node.event_pub.publish(evt)

    def rollover_session(self, *, reason: str) -> None:
        self.node.session.new_session()
        invalidated = self.node.command_center.rollover_session(self.node.session.generation)
        if invalidated:
            self.emit_event('bridge_session_rollover', reason=reason, invalidated=[item.to_dict() for item in invalidated])

    def start_handshake(self) -> None:
        seq = self.node._next_seq()
        try:
            self.node.session.mark_handshaking()
            self.node.adapter.query_capabilities(seq)
            self.emit_event('bridge_handshake_started', seq=seq)
        except Exception as exc:
            self.node.session.mark_degraded()
            self.emit_event('bridge_handshake_failed', error=str(exc))

    def build_station_detail(self, detail: dict[str, Any] | None = None) -> dict[str, Any]:
        detail_payload = dict(detail or {})
        detail_payload.setdefault('trace_id', self.node.trace_id)
        detail_payload.setdefault('pending_commands', self.node.command_center.snapshot())
        detail_payload.setdefault('capabilities', self.node.capabilities.to_dict())
        detail_payload.setdefault('session', self.node.session.snapshot())
        detail_payload.setdefault('reset_sync', self.node.reset_sync.snapshot())
        return detail_payload

    def publish_station(
        self,
        state_name: str,
        *,
        sensor: bool = False,
        gate_busy: bool = False,
        sorter_busy: bool = False,
        fault_code: str = '',
        detail: dict[str, Any] | None = None,
    ) -> None:
        detail_payload = self.build_station_detail(detail)
        msg = StationState()
        msg.stamp = self.node.get_clock().now().to_msg()
        msg.state = state_name
        msg.batch_id = self.node.batch_id
        msg.item_id = self.node.item_id
        msg.sensor_in_position = sensor
        msg.gate_busy = gate_busy
        msg.sorter_busy = sorter_busy
        msg.estop = False
        msg.fault_code = fault_code
        msg.detail = json.dumps(detail_payload, ensure_ascii=False, sort_keys=True)
        self.node.state_pub.publish(msg)
        self.emit_event('bridge_state', state=state_name, detail=detail_payload)

    def publish_heartbeat(self) -> None:
        if not self.node.is_active():
            return
        seq = self.node._next_seq()
        self.node.adapter.send_heartbeat(seq)
        self.publish_station(
            'HEARTBEAT',
            detail={'message': 'bridge_alive', 'seq': seq, 'session_id': self.node.session.session_id, 'generation': self.node.session.generation},
        )

    def pending_or_orphan(self, signal: BridgeSignal, command_name: str, detail: dict[str, Any]) -> object | None:
        pending = self.node.command_center.resolve(signal.seq)
        if pending is None:
            orphan = self.node.command_center.tracker.record_orphan_response(
                signal.seq,
                command_name,
                reason=f'orphan_{signal.state.lower()}',
                trace_id=str(detail.get('trace_id', '')),
                item_id=int(detail.get('item_id', -1)),
                batch_id=str(detail.get('batch_id', '')),
                session_generation=self.node.session.generation,
            )
            self.emit_event('bridge_orphan_response', signal_state=signal.state, pending=orphan.to_dict())
            return None
        detail.setdefault('trace_id', pending.trace_id)
        detail.setdefault('item_id', pending.item_id)
        detail.setdefault('batch_id', pending.batch_id)
        detail.setdefault('session_generation', pending.session_generation)
        return pending

    def handle_adapter_signal(self, signal: BridgeSignal) -> None:
        self.node.watchdog.observe()
        detail = dict(signal.detail or {})
        detail.setdefault('seq', signal.seq)
        detail.setdefault('session_generation', self.node.session.generation)
        if signal.state == 'FEED_ACK':
            pending = self.pending_or_orphan(signal, 'feed', detail)
            if pending is not None:
                self.node.command_center.tracker.mark_ack(signal.seq, session_generation=self.node.session.generation)
            self.publish_station('FEED_ACK', gate_busy=True, detail=detail)
        elif signal.state == 'POSITION_READY':
            self.pending_or_orphan(signal, 'feed', detail)
            self.publish_station('POSITION_READY', sensor=True, detail=detail)
        elif signal.state == 'SORT_ACK':
            pending = self.pending_or_orphan(signal, 'sort', detail)
            if pending is not None:
                self.node.command_center.tracker.mark_ack(signal.seq, session_generation=self.node.session.generation)
            self.publish_station('SORT_ACK', sorter_busy=True, detail=detail)
        elif signal.state == 'SORT_DONE':
            pending = self.pending_or_orphan(signal, 'sort', detail)
            if pending is not None:
                self.node.command_center.tracker.mark_done(signal.seq, session_generation=self.node.session.generation)
            self.publish_station('SORT_DONE', detail=detail)
        elif signal.state == 'FAULT':
            code = signal.fault_code or str(detail.get('fault_code', 'FAULT_BRIDGE'))
            self.publish_fault(code, detail)
        elif signal.state == 'RESET_ACK':
            pending = self.pending_or_orphan(signal, 'reset', detail)
            if pending is not None:
                self.node.command_center.tracker.mark_ack(signal.seq, session_generation=self.node.session.generation)
            self.node.reset_sync.complete()
            self.rollover_session(reason='reset_ack')
            self.publish_station('RESET_ACK', detail=detail)
            self.start_handshake()
        elif signal.state == 'HEARTBEAT':
            try:
                normalized_heartbeat = validate_runtime_protocol_version(
                    detail,
                    configured_version=getattr(self.node, 'protocol_version_label', 'v1'),
                    contract=getattr(self.node, 'protocol_contract', None),
                    required=bool(getattr(getattr(self.node, 'protocol_contract', None), 'heartbeat_version_required', False)),
                ) if getattr(self.node, 'protocol_contract', None) is not None else dict(detail)
            except StationProtocolContractError as exc:
                self.publish_fault(
                    'FAULT_PROTOCOL_CONTRACT',
                    {
                        'phase': 'HEARTBEAT',
                        'error': str(exc),
                        'reported_detail': detail,
                        'configured_protocol_version': getattr(self.node, 'protocol_version_label', 'v1'),
                    },
                )
                return
            self.emit_event('bridge_heartbeat', seq=signal.seq, detail=normalized_heartbeat)
        elif signal.state == 'CAPABILITIES':
            merged_detail = dict(detail)
            merged_detail.setdefault('protocol_version', getattr(self.node, 'protocol_version_label', 'v1'))
            configured_codes = sorted(int(item) for item in getattr(self.node, 'supported_action_codes', set()))
            if configured_codes:
                merged_detail.setdefault('supported_action_codes', configured_codes)
            try:
                validated_capabilities = validate_capabilities_payload(
                    merged_detail,
                    configured_version=getattr(self.node, 'protocol_version_label', 'v1'),
                    configured_action_codes=getattr(self.node, 'supported_action_codes', set()),
                    expected_features=getattr(self.node, 'expected_station_features', set()),
                    contract=getattr(self.node, 'protocol_contract', None),
                ) if getattr(self.node, 'protocol_contract', None) is not None else merged_detail
            except StationProtocolContractError as exc:
                self.node.handshake_done = False
                self.publish_fault(
                    'FAULT_PROTOCOL_CONTRACT',
                    {
                        'phase': 'CAPABILITIES',
                        'error': str(exc),
                        'reported_detail': merged_detail,
                        'configured_protocol_version': getattr(self.node, 'protocol_version_label', 'v1'),
                        'configured_action_codes': configured_codes,
                    },
                )
                return
            self.node.capabilities = StationCapabilities.from_payload(validated_capabilities)
            self.node.handshake_done = True
            self.node.session.mark_ready(device_id=str(validated_capabilities.get('device_id', '')), capabilities=self.node.capabilities.to_dict())
            self.emit_event('bridge_handshake_complete', capabilities=self.node.capabilities.to_dict())
            self.publish_station('CAPABILITIES', detail=validated_capabilities)

    def publish_fault(self, code: str, detail: dict[str, Any] | None = None) -> None:
        fault = FaultEvent()
        fault.stamp = self.node.get_clock().now().to_msg()
        fault.level = 'ERROR'
        fault.fault_code = code
        fault.source_node = 'station_bridge_node'
        fault.description = json.dumps(detail or {}, ensure_ascii=False, sort_keys=True)
        fault.recoverable = True
        self.node.fault_pub.publish(fault)
        self.node.session.mark_degraded()
        self.publish_station('FAULT', fault_code=code, detail=detail or {'fault_code': code})

    def check_stale_commands(self) -> None:
        if not self.node.is_active():
            return
        timeout_sec = float(self.node.get_parameter('ack_stale_timeout_sec').value)
        stale = self.node.command_center.tracker.stale(timeout_sec, mark=True, session_generation=self.node.session.generation)
        for pending in stale:
            self.emit_event(
                'bridge_pending_stale',
                seq=pending.seq,
                command_name=pending.command_name,
                item_id=pending.item_id,
                trace_id=pending.trace_id,
                acked=pending.acked,
                state=pending.state,
                terminal_reason=pending.terminal_reason,
            )

    def watchdog_tick(self) -> None:
        if self.node.lifecycle_state in {'UNCONFIGURED', 'FINALIZED'}:
            return
        if self.node.watchdog.expired():
            self.node.session.mark_degraded()
            self.node.session.reconnect_attempts += 1
            self.node.next_reconnect_at = time.monotonic() + self.node.reconnect_policy.delay_for_attempt(self.node.session.reconnect_attempts)
            self.publish_station(
                'HEARTBEAT_LOST',
                fault_code='FAULT_HEARTBEAT_LOST',
                detail={
                    'reason': 'watchdog_expired',
                    'next_reconnect_at': round(self.node.next_reconnect_at, 6),
                    'generation': self.node.session.generation,
                },
            )
            self.node.watchdog.observe()
            return
        if self.node.session.phase.value == 'DEGRADED' and self.node.next_reconnect_at:
            now = time.monotonic()
            if now >= self.node.next_reconnect_at:
                self.rollover_session(reason='watchdog_reconnect')
                self.node.session.mark_reconnecting()
                self.start_handshake()
                self.node.next_reconnect_at = 0.0
