from __future__ import annotations

import json
import sys
import types
from pathlib import Path


def _install_runtime_stubs() -> None:
    if 'rclpy' not in sys.modules:
        rclpy = types.ModuleType('rclpy')
        rclpy.init = lambda *args, **kwargs: None
        rclpy.shutdown = lambda *args, **kwargs: None
        sys.modules['rclpy'] = rclpy

    if 'rclpy.node' not in sys.modules:
        node_mod = types.ModuleType('rclpy.node')

        class Node:
            def __init__(self, *args, **kwargs) -> None:
                pass

        node_mod.Node = Node
        sys.modules['rclpy.node'] = node_mod

    if 'rclpy.lifecycle' not in sys.modules:
        lifecycle_mod = types.ModuleType('rclpy.lifecycle')

        class LifecycleNode:
            def __init__(self, *args, **kwargs) -> None:
                pass

        lifecycle_mod.LifecycleNode = LifecycleNode
        sys.modules['rclpy.lifecycle'] = lifecycle_mod

    if 'std_msgs' not in sys.modules:
        std_msgs = types.ModuleType('std_msgs')
        sys.modules['std_msgs'] = std_msgs
    if 'std_msgs.msg' not in sys.modules:
        std_msgs_msg = types.ModuleType('std_msgs.msg')

        class String:
            def __init__(self) -> None:
                self.data = ''

        std_msgs_msg.String = String
        sys.modules['std_msgs.msg'] = std_msgs_msg

    if 'inspection_interfaces' not in sys.modules:
        sys.modules['inspection_interfaces'] = types.ModuleType('inspection_interfaces')

    if 'inspection_interfaces.msg' not in sys.modules:
        msg_mod = types.ModuleType('inspection_interfaces.msg')

        class ControlCommand:
            def __init__(self) -> None:
                self.command = ''
                self.source = ''
                self.reason = ''
                self.batch_id = ''
                self.item_id = -1
                self.trace_id = ''
                self.schema_version = 'v1'
                self.payload_json = ''

        class DiagnosticsSnapshot:
            def __init__(self) -> None:
                self.payload_json = '{}'

        class SupervisorStateEnvelope:
            pass

        class CaptureRequest:
            def __init__(self) -> None:
                self.trace_id = ''
                self.batch_id = ''
                self.item_id = -1
                self.frame_index = -1
                self.source = ''
                self.schema_version = 'v1'
                self.payload_json = ''

        class CountStats: pass
        class FaultEvent: pass
        class InspectionResult: pass
        class SortCommand: pass
        class StationState: pass
        class ActionExecutorEvent: pass

        msg_mod.ControlCommand = ControlCommand
        msg_mod.DiagnosticsSnapshot = DiagnosticsSnapshot
        msg_mod.SupervisorStateEnvelope = SupervisorStateEnvelope
        msg_mod.CaptureRequest = CaptureRequest
        msg_mod.CountStats = CountStats
        msg_mod.FaultEvent = FaultEvent
        msg_mod.InspectionResult = InspectionResult
        msg_mod.SortCommand = SortCommand
        msg_mod.StationState = StationState
        msg_mod.ActionExecutorEvent = ActionExecutorEvent
        sys.modules['inspection_interfaces.msg'] = msg_mod

    if 'inspection_interfaces.srv' not in sys.modules:
        srv_mod = types.ModuleType('inspection_interfaces.srv')

        class _EmptyRequest:
            pass

        class ResetFault:
            Request = _EmptyRequest

        class StartInspection:
            Request = _EmptyRequest

        srv_mod.ResetFault = ResetFault
        srv_mod.StartInspection = StartInspection
        sys.modules['inspection_interfaces.srv'] = srv_mod


def _ensure_workspace_on_path() -> None:
    root = Path(__file__).resolve().parents[2]
    src = root / 'src'
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def test_supervisor_runtime_callback_smoke_executes_node_name_normalization() -> None:
    _install_runtime_stubs()
    _ensure_workspace_on_path()
    from inspection_supervisor.supervisor_node import SupervisorNode

    class _Registry:
        def __init__(self) -> None:
            self.calls = []

        def ingest_event(self, node, **kwargs):
            self.calls.append((node, kwargs))

    node = SupervisorNode.__new__(SupervisorNode)
    node.registry = _Registry()

    message = types.SimpleNamespace(data=json.dumps({'node': 'fsm_node', 'type': 'heartbeat', 'state': 'active'}))
    SupervisorNode.on_event(node, message)

    assert node.registry.calls
    normalized_node, payload = node.registry.calls[0]
    assert normalized_node == 'inspection_fsm_node'
    assert payload['state'] == 'ACTIVE'


def test_orchestrator_runtime_callbacks_and_publish_action_are_importable() -> None:
    _install_runtime_stubs()
    _ensure_workspace_on_path()
    from inspection_orchestrator.orchestrator_node import OrchestratorNode

    published = []

    class _Publisher:
        def publish(self, msg):
            published.append(msg)

    node = OrchestratorNode.__new__(OrchestratorNode)
    node.control_pub = _Publisher()
    node.typed_control_pub = _Publisher()

    OrchestratorNode.publish_action(node, 'pause', reason='smoke_test')

    assert len(published) == 2
    typed = published[-1]
    assert typed.command == 'pause'
    assert typed.source == 'inspection_orchestrator_node'
    assert '"command":"pause"' in typed.payload_json.replace(' ', '')


def test_fsm_typed_control_bridge_synthesizes_legacy_payload_without_payload_json() -> None:
    _install_runtime_stubs()
    _ensure_workspace_on_path()
    from inspection_fsm.fsm_node import FSMNode

    captured = []

    node = FSMNode.__new__(FSMNode)
    node.on_control_message = lambda msg: captured.append(json.loads(msg.data))

    typed = types.SimpleNamespace(
        command='resume',
        source='inspection_supervisor_node',
        reason='bridge_test',
        batch_id='B-1',
        item_id=3,
        trace_id='T-9',
        schema_version='v1',
        payload_json='',
    )
    FSMNode.on_typed_control_message(node, typed)

    assert captured
    payload = captured[0]
    assert payload['type'] == 'typed_control_bridge'
    assert payload['command'] == 'resume'
    assert payload['source'] == 'inspection_supervisor_node'
    assert payload['trace_id'] == 'T-9'


def test_capture_request_transport_helpers_round_trip_without_payload_json() -> None:
    _install_runtime_stubs()
    _ensure_workspace_on_path()
    from inspection_utils.transport_contracts import capture_request_payload_from_message, populate_capture_request_message

    typed_in = types.SimpleNamespace(
        trace_id='TRACE-CAP',
        batch_id='B-CAP',
        item_id=4,
        frame_index=7,
        source='typed_capture_request',
        schema_version='v1',
        payload_json='',
    )
    payload = capture_request_payload_from_message(typed_in)
    assert payload['type'] == 'capture_request'
    assert payload['trace_id'] == 'TRACE-CAP'
    assert payload['frame_index'] == 7

    from inspection_interfaces.msg import CaptureRequest

    typed_out = CaptureRequest()
    populate_capture_request_message(
        typed_out,
        'TRACE-CAP',
        batch_id='B-CAP',
        item_id=4,
        frame_index=7,
        source='inspection_fsm_node',
        extra={'cycle_index': 9},
    )
    assert typed_out.trace_id == 'TRACE-CAP'
    assert '"trace_id":"TRACE-CAP"' in typed_out.payload_json.replace(' ', '')
    assert '"cycle_index":9' in typed_out.payload_json.replace(' ', '')


def test_fsm_publish_capture_request_keeps_legacy_and_typed_payloads_aligned() -> None:
    _install_runtime_stubs()
    _ensure_workspace_on_path()
    from inspection_fsm.fsm_node import FSMNode

    published = []

    class _Publisher:
        def publish(self, msg):
            published.append(msg)

    class _Artifacts:
        def __init__(self) -> None:
            self.calls = []

        def set(self, key, value):
            self.calls.append((key, value))

    node = FSMNode.__new__(FSMNode)
    node.capture_pub = _Publisher()
    node.typed_capture_pub = _Publisher()
    node.data = types.SimpleNamespace(item_id=5, batch_id='B-5', trace_id='T-5', cycle_index=11)
    artifacts = _Artifacts()
    node.runtime = types.SimpleNamespace(current=types.SimpleNamespace(artifacts=artifacts))
    node.emit_event = lambda *args, **kwargs: None

    FSMNode.publish_capture_request(node)

    assert len(published) == 2
    legacy = published[0]
    typed = published[1]
    payload = json.loads(legacy.data)
    assert payload['type'] == 'capture_request'
    assert payload['trace_id'] == 'T-5'
    assert payload['cycle_index'] == 11
    assert typed.trace_id == 'T-5'
    assert '"trace_id":"T-5"' in typed.payload_json.replace(' ', '')
    assert '"cycle_index":11' in typed.payload_json.replace(' ', '')
    assert artifacts.calls
