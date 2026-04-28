from __future__ import annotations

import copy
from typing import Any

from std_msgs.msg import String

from inspection_interfaces.msg import InspectionResult, SortCommand, StationState
from inspection_utils.transport_common import START_COMMAND, extract_control_command
from inspection_utils.logging_common import safe_json_loads
from inspection_utils.config_common import parameter_as_bool
from inspection_utils.transport_common import normalized_payload_from_typed_message
from inspection_utils.runtime_event_contracts import RuntimeEventDeduper, normalize_runtime_event_message

from .control_dispatch import dispatch_control_command
from .fsm_core import StationEvent, StationPhase
from .ownership_rules import check_binding, check_station_detail


class FsmIngressAdapter:
    """Translate ROS ingress messages into canonical station events."""

    def __init__(self, node: Any) -> None:
        self.node = node
        self._runtime_event_deduper = RuntimeEventDeduper(max_entries=128, ttl_sec=2.0)

    def _drop_mismatched_payload(self, event_name: str, payload: dict, *, station_state: bool = False) -> bool:
        check = check_station_detail(self.node.data.trace_id, self.node.data.item_id, payload) if station_state else check_binding(self.node.data.trace_id, self.node.data.item_id, payload, allow_missing_trace=False)
        if check.ok:
            return False
        self.node.emit_event(event_name, reason=check.reason, expected_trace_id=self.node.data.trace_id, expected_item_id=self.node.data.item_id, payload=payload)
        return True

    def on_control_message(self, msg: String) -> None:
        if self.node._runtime_input_blocked('topic:/inspection/control'):
            return
        payload = safe_json_loads(msg.data, {'action': msg.data})
        self.on_control_payload(payload)

    def on_control_payload(self, payload: dict[str, Any]) -> None:
        action = extract_control_command(payload)
        if action == START_COMMAND:
            self.node.emit_event('control_ignored', reason='start_requires_service', payload=payload)
            return
        dispatch = dispatch_control_command(action)
        if dispatch is None:
            self.node.emit_event('control_ignored', reason='unknown_action', payload=payload)
            return
        event = dispatch.event
        if event in {StationEvent.ENTER_MANUAL, StationEvent.MANUAL_STEP_FEED, StationEvent.MANUAL_STEP_CAPTURE, StationEvent.MANUAL_STEP_SORT}:
            if not parameter_as_bool(self.node, 'allow_manual_mode', default=False):
                self.node.emit_event('control_ignored', reason='manual_mode_disabled', payload=payload)
                return
        if event in {StationEvent.MANUAL_STEP_FEED, StationEvent.MANUAL_STEP_CAPTURE, StationEvent.MANUAL_STEP_SORT}:
            self.node.runtime.record_manual_action(dispatch.command, trace_id=self.node.data.trace_id, item_id=self.node.data.item_id)
        if dispatch.compatibility_mode:
            self.node.emit_event('control_compatibility_bridge', command=dispatch.command, event=event.value)
        self.node.apply_event(event, dispatch.detail_reason or f'control:{dispatch.command}')

    def on_typed_control_message(self, msg: object) -> None:
        payload = normalized_payload_from_typed_message(msg, default_event_type='typed_control_bridge', bridge_name='control')
        self.on_control_payload(payload)

    def _handle_vision_frame_payload(self, payload: dict[str, Any], *, source: str) -> None:
        if self.node._runtime_input_blocked(source):
            return
        event_type = str(payload.get('type', ''))
        if event_type != 'vision_frame_acquired':
            return
        if self._runtime_event_deduper.seen_recently(payload):
            return
        if self.node.data.phase != StationPhase.CAPTURE_WAIT_FRAME:
            self.node.emit_event('fsm_drop_capture_event', reason='capture_event_outside_capture_phase', payload=payload)
            return
        if self._drop_mismatched_payload('fsm_drop_capture_event', payload):
            return
        self.node.runtime.current.artifacts.set('vision_frame_event', payload)
        self.node.apply_event(StationEvent.CAPTURE_DONE, f"vision_frame:{int(payload.get('item_id', -1))}")

    def on_event_message(self, msg: String) -> None:
        self._handle_vision_frame_payload(safe_json_loads(msg.data), source='topic:/inspection/events')

    def on_typed_vision_event_message(self, msg: object) -> None:
        self._handle_vision_frame_payload(
            normalize_runtime_event_message(msg, default_event_type='vision_frame_acquired'),
            source='topic:/inspection/events/vision_frame_acquired_typed',
        )

    def on_station_state(self, msg: StationState) -> None:
        if self.node._runtime_input_blocked('topic:/station/state'):
            return
        state = (msg.state or '').upper()
        detail = safe_json_loads(msg.detail or '{}')
        if isinstance(detail.get('pending_commands'), list):
            self.node.runtime.current.update_pending_commands(detail.get('pending_commands', []))
        if isinstance(detail.get('session'), dict):
            self.node.runtime.current.artifacts.set('bridge_session', detail.get('session'))
        item_scoped_states = {'FEED_ACK', 'POSITION_READY', 'SORT_ACK', 'SORT_DONE', 'RESET_ACK'}
        if state in item_scoped_states and self._drop_mismatched_payload('fsm_drop_station_state', detail, station_state=True):
            return
        if state == 'FEED_ACK':
            self.node.apply_event(StationEvent.FEED_ACK, f'bridge:{state}')
        elif state == 'POSITION_READY':
            self.node.apply_event(StationEvent.POSITION_READY, f'bridge:{state}')
        elif state == 'SORT_ACK':
            self.node.apply_event(StationEvent.SORT_ACK, f'bridge:{state}')
        elif state == 'SORT_DONE':
            self.node.apply_event(StationEvent.SORT_DONE, f'bridge:{state}')
        elif state == 'RESET_ACK':
            self.node.apply_event(StationEvent.RECOVERY_OK, f'bridge:{state}')
        elif state == 'HEARTBEAT_LOST':
            self.node.raise_fault('FAULT_HEARTBEAT_LOST', msg.detail or 'bridge heartbeat lost', event=StationEvent.HEARTBEAT_LOST)
        elif state == 'FAULT':
            self.node.raise_fault(msg.fault_code or 'FAULT_BRIDGE', msg.detail or 'bridge fault')

    def on_result(self, msg: InspectionResult) -> None:
        if self.node._runtime_input_blocked('topic:/inspection/result'):
            return
        if self.node.data.phase != StationPhase.ANALYZE_WAIT:
            self.node.emit_event('fsm_drop_result', reason='result_outside_analyze_phase', actual_phase=self.node.data.phase.value, actual_item_id=msg.item_id)
            return
        detail = safe_json_loads(msg.detail_json or '{}')
        detail.setdefault('item_id', msg.item_id)
        if self._drop_mismatched_payload('fsm_drop_result', detail):
            return
        self.node.last_result_detail = detail
        self.node.runtime.current.attach_result(detail)
        self.node.apply_event(StationEvent.RESULT_READY, f'vision_result:{msg.item_id}')

    def on_decision_output(self, msg: SortCommand) -> None:
        """Consume one decision output and buffer it for guarded execution.

        Args:
            msg: Decision payload produced by ``decision_node``.

        Returns:
            None.

        Raises:
            No exception is raised beyond payload binding checks.

        Boundary behavior:
            Decisions observed outside ``DECISION_WAIT`` are buffered but do not
            immediately dispatch a station command. Actual execution remains a
            state-machine egress decision.
        """
        if self.node._runtime_input_blocked('topic:/inspection/decision_output'):
            return
        reason_payload = safe_json_loads(msg.reason or '{}', {'trace_id': '', 'item_id': msg.item_id})
        reason_payload.setdefault('item_id', msg.item_id)
        if self._drop_mismatched_payload('fsm_drop_decision', reason_payload):
            return
        self.node.last_sort_cmd = copy.deepcopy(msg)
        self.node.runtime.current.attach_decision(reason_payload)
        if self.node.data.phase != StationPhase.DECISION_WAIT:
            self.node.emit_event('fsm_buffered_decision', decision=msg.decision, payload=reason_payload)
            return
        self.node.current_decision = msg.decision
        self.node.apply_event(StationEvent.DECISION_READY, f'decision:{msg.decision}')
