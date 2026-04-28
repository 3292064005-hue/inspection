from __future__ import annotations

"""Bridge-side session coordination.

The coordinator centralizes session, handshake, ACK, reset, and watchdog
transitions so :mod:`station_bridge_node` can stay a thin ROS shell.
"""

import json
from typing import Any

from inspection_utils.logging_common import safe_json_loads

from .bridge_base import BridgeSignal
from .runtime_support import BridgeRuntimeSupport


class BridgeSessionCoordinator:
    """Coordinate station bridge protocol/session state transitions."""

    def __init__(self, node: Any) -> None:
        self.node = node
        self.runtime_support = BridgeRuntimeSupport(node)

    def close_adapter(self) -> tuple[bool, str]:
        return self.runtime_support.close_adapter()

    def start_handshake(self) -> None:
        self.runtime_support.start_handshake()

    def publish_station(self, state_name: str, sensor: bool = False, gate_busy: bool = False, sorter_busy: bool = False, fault_code: str = '', detail: dict | None = None) -> None:
        self.runtime_support.publish_station(state_name, sensor=sensor, gate_busy=gate_busy, sorter_busy=sorter_busy, fault_code=fault_code, detail=detail)

    def publish_heartbeat(self) -> None:
        self.runtime_support.publish_heartbeat()

    def on_feed_request(self, raw_data: str) -> None:
        if not self.node.is_active():
            return
        request = safe_json_loads(raw_data)
        request.setdefault('protocol_version', getattr(self.node, 'protocol_version_label', 'v1'))
        self.node.batch_id = str(request.get('batch_id', 'BATCH_DEMO'))
        self.node.item_id = int(request.get('item_id', self.node.item_id + 1))
        self.node.trace_id = str(request.get('trace_id', f'{self.node.batch_id}-{self.node.item_id:05d}'))
        seq = self.node._next_seq()
        self.node.command_center.register(seq, 'feed', self.node.trace_id, self.node.item_id, self.node.batch_id)
        self.publish_station('FEEDING', gate_busy=True, detail={'command': 'feed_one', 'seq': seq, 'generation': self.node.session.generation})
        self.node.adapter.send_feed(seq, json.dumps(request, ensure_ascii=False, sort_keys=True).encode('utf-8'))

    def on_sort_request(self, msg: Any) -> None:
        if not self.node.is_active():
            return
        self.node.batch_id = msg.batch_id
        self.node.item_id = msg.item_id
        reason_data = safe_json_loads(msg.reason or '{}', {'reason': msg.reason})
        self.node.trace_id = str(reason_data.get('trace_id', self.node.trace_id or f'{self.node.batch_id}-{self.node.item_id:05d}'))
        supported_action_codes = getattr(self.node, 'supported_action_codes', set())
        if supported_action_codes and int(msg.action_code) not in supported_action_codes:
            self.publish_fault(
                'FAULT_UNSUPPORTED_ACTION_CODE',
                {
                    'action_code': int(msg.action_code),
                    'supported_action_codes': sorted(int(item) for item in supported_action_codes),
                    'trace_id': self.node.trace_id,
                    'item_id': self.node.item_id,
                    'batch_id': self.node.batch_id,
                },
            )
            return
        seq = self.node._next_seq()
        retry_index = int(reason_data.get('retry_index', 0))
        self.node.command_center.register(seq, 'sort', self.node.trace_id, self.node.item_id, self.node.batch_id, retry_index=retry_index)
        detail = {
            'command': 'sort_to_bin',
            'decision': msg.decision,
            'action_code': msg.action_code,
            'target_bin': msg.target_bin,
            'seq': seq,
            'retry_index': retry_index,
            'generation': self.node.session.generation,
        }
        self.publish_station('SORTING', sorter_busy=True, detail=detail)
        payload = {
            'protocol_version': getattr(self.node, 'protocol_version_label', 'v1'),
            'decision': msg.decision,
            'action_code': msg.action_code,
            'target_bin': msg.target_bin,
            'trace_id': self.node.trace_id,
            'item_id': self.node.item_id,
            'batch_id': self.node.batch_id,
            'session_generation': self.node.session.generation,
        }
        self.node.adapter.send_sort(seq, json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8'))

    def on_reset_request(self, raw_data: str) -> None:
        if self.node.lifecycle_state == 'FINALIZED':
            return
        payload = safe_json_loads(raw_data)
        payload.setdefault('protocol_version', getattr(self.node, 'protocol_version_label', 'v1'))
        self.node.trace_id = str(payload.get('trace_id', self.node.trace_id))
        seq = self.node._next_seq()
        self.node.command_center.register(seq, 'reset', self.node.trace_id, self.node.item_id, self.node.batch_id)
        self.node.reset_sync.start(seq)
        self.node.session.mark_resetting()
        self.node.adapter.reset_fault(seq, json.dumps(payload, ensure_ascii=False, sort_keys=True).encode('utf-8'))
        self.publish_station('RESETTING', detail={'seq': seq, 'fault_code': payload.get('fault_code', ''), 'session_id': self.node.session.session_id, 'generation': self.node.session.generation})

    def handle_adapter_signal(self, signal: BridgeSignal) -> None:
        self.runtime_support.handle_adapter_signal(signal)

    def publish_fault(self, code: str, detail: dict | None = None) -> None:
        self.runtime_support.publish_fault(code, detail)

    def poll_adapter(self) -> None:
        if self.node.lifecycle_state in {'UNCONFIGURED', 'FINALIZED'}:
            return
        self.node.adapter.poll()

    def check_stale_commands(self) -> None:
        self.runtime_support.check_stale_commands()

    def watchdog_tick(self) -> None:
        self.runtime_support.watchdog_tick()
