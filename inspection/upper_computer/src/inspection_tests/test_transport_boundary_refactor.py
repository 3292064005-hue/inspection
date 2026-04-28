from __future__ import annotations

import ast
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

CORE_RUNTIME_MODULES = [
    'inspection_fsm/inspection_fsm/fsm_ingress.py',
    'inspection_logger/inspection_logger/logger_node.py',
    'inspection_supervisor/inspection_supervisor/supervisor_node.py',
    'inspection_orchestrator/inspection_orchestrator/orchestrator_node.py',
    'vision_processing/vision_processing/processor_node.py',
]


def _install_runtime_stubs() -> None:
    if 'std_msgs' not in sys.modules:
        sys.modules['std_msgs'] = types.ModuleType('std_msgs')
    if 'std_msgs.msg' not in sys.modules:
        std_msgs_msg = types.ModuleType('std_msgs.msg')

        class String:
            def __init__(self) -> None:
                self.data = ''

        std_msgs_msg.String = String
        sys.modules['std_msgs.msg'] = std_msgs_msg

    if 'inspection_interfaces' not in sys.modules:
        sys.modules['inspection_interfaces'] = types.ModuleType('inspection_interfaces')

    msg_mod = sys.modules.get('inspection_interfaces.msg')
    if msg_mod is None:
        msg_mod = types.ModuleType('inspection_interfaces.msg')
        sys.modules['inspection_interfaces.msg'] = msg_mod

    if not hasattr(msg_mod, 'ControlCommand'):
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
        msg_mod.ControlCommand = ControlCommand

    if not hasattr(msg_mod, 'DiagnosticsSnapshot'):
        class DiagnosticsSnapshot:
            def __init__(self) -> None:
                self.payload_json = '{}'
                self.node_name = ''
                self.status = ''
                self.lifecycle_state = ''
        msg_mod.DiagnosticsSnapshot = DiagnosticsSnapshot

    if not hasattr(msg_mod, 'SupervisorStateEnvelope'):
        class SupervisorStateEnvelope:
            def __init__(self) -> None:
                self.payload_json = '{}'
                self.node = ''
                self.profile_name = ''
                self.current_mode = ''
        msg_mod.SupervisorStateEnvelope = SupervisorStateEnvelope

    if not hasattr(msg_mod, 'SupervisorCommand'):
        class SupervisorCommand:
            def __init__(self) -> None:
                self.command = ''
                self.target_mode = ''
                self.reason = ''
                self.source = ''
                self.schema_version = 'v1'
                self.payload_json = ''
        msg_mod.SupervisorCommand = SupervisorCommand

    if not hasattr(msg_mod, 'CaptureRequest'):
        class CaptureRequest:
            def __init__(self) -> None:
                self.trace_id = ''
                self.batch_id = ''
                self.item_id = -1
                self.frame_index = -1
                self.source = ''
                self.schema_version = 'v1'
                self.payload_json = ''
        msg_mod.CaptureRequest = CaptureRequest

    for simple_name in [
        'CountStats',
        'FaultEvent',
        'InspectionResult',
        'SortCommand',
        'StationState',
        'ActionExecutorEvent',
        'FsmTransitionEvent',
        'VisionFrameAcquiredEvent',
        'DecisionPublishedEvent',
        'BridgeHeartbeatEvent',
        'BridgeHandshakeCompleteEvent',
        'FaultRaisedEvent',
    ]:
        if not hasattr(msg_mod, simple_name):
            setattr(msg_mod, simple_name, type(simple_name, (), {}))


def _ensure_workspace_on_path() -> None:
    root = Path(__file__).resolve().parents[2]
    src = root / 'src'
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


def _normalized_payload_from_typed_message():
    _install_runtime_stubs()
    _ensure_workspace_on_path()
    from inspection_utils.transport_adapters import normalized_payload_from_typed_message

    return normalized_payload_from_typed_message


def _module_imports(relative_path: str) -> set[str]:
    tree = ast.parse((REPO_ROOT / relative_path).read_text(encoding='utf-8'))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported_names = ','.join(alias.name for alias in node.names)
            imports.add(f'{node.module}:{imported_names}')
    return imports


def test_core_runtime_modules_no_longer_depend_on_legacy_payload_bridge() -> None:
    for relative_path in CORE_RUNTIME_MODULES:
        imports = _module_imports(relative_path)
        assert 'inspection_utils.transport_adapters:legacy_payload_json_from_typed_message' not in imports


def test_normalized_payload_from_typed_message_returns_structured_supervisor_command_without_serializing() -> None:
    normalize = _normalized_payload_from_typed_message()
    typed = types.SimpleNamespace(
        command='set_mode',
        target_mode='AUTO',
        reason='integration_test',
        source='gateway',
        schema_version='v1',
        payload_json='',
    )
    payload = normalize(typed, default_event_type='supervisor_command', bridge_name='supervisor_command')
    assert payload['type'] == 'supervisor_command'
    assert payload['command'] == 'set_mode'
    assert payload['mode'] == 'AUTO'
    assert payload['source'] == 'gateway'


def test_normalized_payload_from_typed_message_prefers_payload_json_when_available() -> None:
    normalize = _normalized_payload_from_typed_message()
    typed = types.SimpleNamespace(payload_json='{"type":"diagnostics_snapshot","node":"inspection_supervisor_node","status":"ok"}')
    payload = normalize(typed, default_event_type='diagnostics_snapshot', bridge_name='diagnostics')
    assert payload['type'] == 'diagnostics_snapshot'
    assert payload['node'] == 'inspection_supervisor_node'
    assert payload['status'] == 'ok'



def test_runtime_event_transport_policy_registers_typed_channels() -> None:
    _install_runtime_stubs()
    _ensure_workspace_on_path()
    from inspection_utils.transport_boundary import transport_bridge_policy

    for bridge_name in [
        'fsm_transition',
        'vision_frame_acquired',
        'decision_published',
        'bridge_heartbeat',
        'bridge_handshake_complete',
        'fault_raised',
    ]:
        policy = transport_bridge_policy(bridge_name)
        assert policy.typed_publish_enabled is True
        assert policy.legacy_publish_enabled is False
        assert policy.core_transport == 'typed'


def test_runtime_event_deduper_suppresses_duplicate_dual_transport_payloads() -> None:
    from inspection_utils.runtime_event_contracts import RuntimeEventDeduper

    deduper = RuntimeEventDeduper(ttl_sec=5.0)
    payload = {
        'type': 'decision_published',
        'trace_id': 'TRACE-1',
        'batch_id': 'B-1',
        'item_id': 1,
        'decision': 'OK',
        'action_code': 1,
        'target_bin': 'BIN-OK',
        'matched_rule_id': 'rule-1',
        'matched_rule_priority': 1,
        'confidence': 0.95,
        'severity': 'INFO',
        'output_topic': '/inspection/decision_output',
        'schema_version': 'v1',
    }

    assert deduper.seen_recently(payload) is False
    assert deduper.seen_recently(dict(payload)) is True


def test_runtime_event_deduper_ignores_non_catalog_payloads() -> None:
    from inspection_utils.runtime_event_contracts import RuntimeEventDeduper

    deduper = RuntimeEventDeduper(ttl_sec=5.0)
    payload = {'type': 'cycle_started', 'batch_id': 'B-1'}

    assert deduper.seen_recently(payload) is False
    assert deduper.seen_recently(payload) is False
