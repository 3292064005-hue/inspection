from __future__ import annotations

import json
import sys
import types
from pathlib import Path


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


def _ensure_workspace_on_path() -> None:
    root = Path(__file__).resolve().parents[2]
    src = root / 'src'
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


class _Publisher:
    def __init__(self) -> None:
        self.messages = []

    def publish(self, message) -> None:
        self.messages.append(message)


class _TypedSupervisorCommand:
    def __init__(self) -> None:
        self.command = ''
        self.target_mode = ''
        self.reason = ''
        self.source = ''
        self.schema_version = 'v1'
        self.payload_json = ''


def test_supervisor_command_payload_roundtrip_from_typed_message() -> None:
    _install_runtime_stubs()
    _ensure_workspace_on_path()
    from inspection_utils.transport_contracts import supervisor_command_payload_from_message, supervisor_command_payload_json

    message = _TypedSupervisorCommand()
    message.command = 'set_mode'
    message.target_mode = 'MAINTENANCE'
    message.reason = 'maintenance_request'
    message.source = 'gateway'
    message.payload_json = supervisor_command_payload_json('set_mode', target_mode='MAINTENANCE', reason='maintenance_request', source='gateway')

    payload = supervisor_command_payload_from_message(message)

    assert payload['command'] == 'set_mode'
    assert payload['mode'] == 'MAINTENANCE'
    assert payload['target_mode'] == 'MAINTENANCE'
    assert payload['reason'] == 'maintenance_request'
    assert payload['source'] == 'gateway'


def test_publish_dual_supervisor_command_defaults_to_typed_first_transport() -> None:
    _install_runtime_stubs()
    _ensure_workspace_on_path()
    from inspection_utils.transport_adapters import publish_dual_supervisor_command

    legacy_pub = _Publisher()
    typed_pub = _Publisher()

    payload_json = publish_dual_supervisor_command(
        legacy_publisher=legacy_pub,
        typed_publisher=typed_pub,
        typed_message_cls=_TypedSupervisorCommand,
        command='set_mode',
        target_mode='AUTO',
        reason='resume',
        source='inspection_hmi_gateway',
    )

    assert len(legacy_pub.messages) == 0
    assert len(typed_pub.messages) == 1
    assert typed_pub.messages[0].target_mode == 'AUTO'
    assert json.loads(payload_json)['command'] == 'set_mode'


def test_publish_dual_supervisor_command_can_reenable_legacy_publish(monkeypatch) -> None:
    _install_runtime_stubs()
    _ensure_workspace_on_path()
    from inspection_utils.transport_adapters import publish_dual_supervisor_command

    monkeypatch.setenv('INSPECTION_TRANSPORT_LEGACY_SUPERVISOR_COMMAND_ENABLED', '1')
    legacy_pub = _Publisher()
    typed_pub = _Publisher()

    publish_dual_supervisor_command(
        legacy_publisher=legacy_pub,
        typed_publisher=typed_pub,
        typed_message_cls=_TypedSupervisorCommand,
        command='set_mode',
        target_mode='AUTO',
        reason='resume',
        source='inspection_hmi_gateway',
    )

    assert len(legacy_pub.messages) == 1
    assert len(typed_pub.messages) == 1
    assert json.loads(legacy_pub.messages[0].data)['mode'] == 'AUTO'
