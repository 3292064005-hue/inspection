from __future__ import annotations

"""Typed transport contracts for the compatibility migration period.

This module centralizes the parallel typed-topic contract used during the
transition away from ad-hoc ``std_msgs/String`` JSON payloads. The helpers keep
versioning, normalization, and compatibility logic in one place so publishers
and subscribers do not drift independently.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from .logging_tools import event_to_json, safe_json_loads

CONTROL_TOPIC_TYPED = '/inspection/control_typed'
CAPTURE_REQUEST_TOPIC_TYPED = '/inspection/capture_request_typed'
DIAGNOSTICS_TOPIC_TYPED = '/inspection/diagnostics_typed'
SUPERVISOR_STATE_TOPIC_TYPED = '/inspection/supervisor/state_typed'
SUPERVISOR_COMMAND_TOPIC_TYPED = '/inspection/supervisor/command_typed'
ACTION_EXECUTOR_EVENT_TOPIC_TYPED = '/inspection/action_executor/events_typed'


class TransportContractError(ValueError):
    """Raised when a typed transport payload is structurally invalid."""


@dataclass(frozen=True, slots=True)
class ControlCommandEnvelope:
    command: str
    source: str = ''
    reason: str = ''
    batch_id: str = ''
    item_id: int = -1
    trace_id: str = ''
    schema_version: str = 'v1'

    def to_payload(self) -> dict[str, Any]:
        return {
            'command': self.command,
            'action': self.command,
            'source': self.source,
            'reason': self.reason,
            'batch_id': self.batch_id,
            'item_id': int(self.item_id),
            'trace_id': self.trace_id,
            'schema_version': self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class CaptureRequestEnvelope:
    trace_id: str
    batch_id: str = ''
    item_id: int = -1
    frame_index: int = -1
    source: str = ''
    schema_version: str = 'v1'

    def to_payload(self) -> dict[str, Any]:
        return {
            'trace_id': self.trace_id,
            'batch_id': self.batch_id,
            'item_id': int(self.item_id),
            'frame_index': int(self.frame_index),
            'source': self.source,
            'schema_version': self.schema_version,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticsEnvelope:
    node: str
    event_type: str
    lifecycle_state: str
    schema_version: str = 'v1'
    payload: Mapping[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        normalized = dict(self.payload or {})
        normalized.setdefault('node', self.node)
        normalized.setdefault('type', self.event_type)
        normalized.setdefault('lifecycle_state', self.lifecycle_state)
        normalized.setdefault('schema_version', self.schema_version)
        return normalized


@dataclass(frozen=True, slots=True)
class SupervisorStateEnvelope:
    node: str
    profile_name: str
    current_mode: str
    payload: Mapping[str, Any] | None = None
    schema_version: str = 'v1'

    def to_payload(self) -> dict[str, Any]:
        normalized = dict(self.payload or {})
        normalized.setdefault('node', self.node)
        normalized.setdefault('profile_name', self.profile_name)
        normalized.setdefault('current_mode', self.current_mode)
        normalized.setdefault('schema_version', self.schema_version)
        return normalized


@dataclass(frozen=True, slots=True)
class SupervisorCommandEnvelope:
    command: str
    target_mode: str = ''
    reason: str = ''
    source: str = ''
    payload: Mapping[str, Any] | None = None
    schema_version: str = 'v1'

    def to_payload(self) -> dict[str, Any]:
        normalized = dict(self.payload or {})
        normalized.setdefault('command', self.command)
        normalized.setdefault('mode', self.target_mode)
        normalized.setdefault('target_mode', self.target_mode)
        normalized.setdefault('reason', self.reason)
        normalized.setdefault('source', self.source)
        normalized.setdefault('schema_version', self.schema_version)
        return normalized


@dataclass(frozen=True, slots=True)
class ActionExecutorEventEnvelope:
    job_id: str
    kind: str
    status: str
    source: str = ''
    payload: Mapping[str, Any] | None = None
    schema_version: str = 'v1'

    def to_payload(self) -> dict[str, Any]:
        normalized = dict(self.payload or {})
        normalized.setdefault('jobId', self.job_id)
        normalized.setdefault('kind', self.kind)
        normalized.setdefault('status', self.status)
        normalized.setdefault('source', self.source)
        normalized.setdefault('schema_version', self.schema_version)
        return normalized


def safe_json_dict(raw: str | Mapping[str, Any] | None, fallback: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        payload = safe_json_loads(raw, fallback or {})
        return dict(payload) if isinstance(payload, dict) else dict(fallback or {})
    return dict(fallback or {})


def serialize_payload(event_type: str, payload: Mapping[str, Any] | None = None) -> str:
    normalized = dict(payload or {})
    if 'type' not in normalized:
        return event_to_json(event_type, **normalized)
    return event_to_json(str(normalized.get('type') or event_type), **{k: v for k, v in normalized.items() if k != 'type'})


def control_envelope_from_payload(payload: Mapping[str, Any] | None) -> ControlCommandEnvelope:
    data = dict(payload or {})
    command = str(data.get('command', data.get('action', ''))).strip()
    if not command:
        raise TransportContractError('control payload missing command/action')
    return ControlCommandEnvelope(
        command=command,
        source=str(data.get('source', '')),
        reason=str(data.get('reason', '')),
        batch_id=str(data.get('batch_id', '')),
        item_id=int(data.get('item_id', -1) or -1),
        trace_id=str(data.get('trace_id', '')),
        schema_version=str(data.get('schema_version', 'v1') or 'v1'),
    )


def capture_request_from_payload(payload: Mapping[str, Any] | None) -> CaptureRequestEnvelope:
    data = dict(payload or {})
    trace_id = str(data.get('trace_id', '')).strip()
    if not trace_id:
        raise TransportContractError('capture request missing trace_id')
    return CaptureRequestEnvelope(
        trace_id=trace_id,
        batch_id=str(data.get('batch_id', '')),
        item_id=int(data.get('item_id', -1) or -1),
        frame_index=int(data.get('frame_index', -1) or -1),
        source=str(data.get('source', '')),
        schema_version=str(data.get('schema_version', 'v1') or 'v1'),
    )


def capture_request_payload(trace_id: str, *, batch_id: str = '', item_id: int = -1, frame_index: int = -1, source: str = '', schema_version: str = 'v1', extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a canonical capture-request payload for both legacy and typed transports."""
    envelope = CaptureRequestEnvelope(
        trace_id=str(trace_id).strip(),
        batch_id=str(batch_id),
        item_id=int(item_id if item_id is not None else -1),
        frame_index=int(frame_index if frame_index is not None else -1),
        source=str(source),
        schema_version=str(schema_version or 'v1'),
    )
    if not envelope.trace_id:
        raise TransportContractError('capture request missing trace_id')
    payload = envelope.to_payload()
    payload.update(dict(extra or {}))
    payload['trace_id'] = envelope.trace_id
    payload['batch_id'] = envelope.batch_id
    payload['item_id'] = envelope.item_id
    payload['frame_index'] = envelope.frame_index
    payload['source'] = envelope.source
    payload['schema_version'] = envelope.schema_version
    return payload


def capture_request_payload_json(trace_id: str, *, event_type: str = 'capture_request', batch_id: str = '', item_id: int = -1, frame_index: int = -1, source: str = '', schema_version: str = 'v1', extra: Mapping[str, Any] | None = None) -> str:
    """Serialize a canonical capture request into the legacy JSON event shape."""
    return serialize_payload(
        event_type,
        capture_request_payload(
            trace_id,
            batch_id=batch_id,
            item_id=item_id,
            frame_index=frame_index,
            source=source,
            schema_version=schema_version,
            extra=extra,
        ),
    )


def populate_capture_request_message(message: Any, trace_id: str, *, batch_id: str = '', item_id: int = -1, frame_index: int = -1, source: str = '', schema_version: str = 'v1', event_type: str = 'capture_request', extra: Mapping[str, Any] | None = None) -> str:
    """Populate a ROS typed capture-request message in one place."""
    payload = capture_request_payload(
        trace_id,
        batch_id=batch_id,
        item_id=item_id,
        frame_index=frame_index,
        source=source,
        schema_version=schema_version,
        extra=extra,
    )
    payload_json = serialize_payload(event_type, payload)
    setattr(message, 'trace_id', str(payload['trace_id']))
    setattr(message, 'batch_id', str(payload['batch_id']))
    setattr(message, 'item_id', int(payload['item_id']))
    setattr(message, 'frame_index', int(payload['frame_index']))
    setattr(message, 'source', str(payload['source']))
    setattr(message, 'schema_version', str(payload['schema_version']))
    if hasattr(message, 'payload_json'):
        setattr(message, 'payload_json', payload_json)
    return payload_json


def capture_request_payload_from_message(message: Any, *, default_event_type: str = 'capture_request') -> dict[str, Any]:
    """Recover a canonical capture-request payload from a typed ROS message."""
    raw_payload_json = getattr(message, 'payload_json', '') or ''
    payload = safe_json_dict(raw_payload_json, fallback={}) if raw_payload_json else {}
    trace_id = str(payload.get('trace_id', getattr(message, 'trace_id', ''))).strip()
    if not trace_id:
        raise TransportContractError('typed capture request missing trace_id')
    normalized = capture_request_payload(
        trace_id,
        batch_id=str(payload.get('batch_id', getattr(message, 'batch_id', '')) or ''),
        item_id=int(payload.get('item_id', getattr(message, 'item_id', -1)) or -1),
        frame_index=int(payload.get('frame_index', getattr(message, 'frame_index', -1)) or -1),
        source=str(payload.get('source', getattr(message, 'source', '')) or ''),
        schema_version=str(payload.get('schema_version', getattr(message, 'schema_version', 'v1')) or 'v1'),
        extra={k: v for k, v in payload.items() if k not in {'trace_id', 'batch_id', 'item_id', 'frame_index', 'source', 'schema_version', 'type'}},
    )
    normalized['type'] = str(payload.get('type', default_event_type) or default_event_type)
    return normalized


def supervisor_command_payload(command: str, *, target_mode: str = '', reason: str = '', source: str = '', schema_version: str = 'v1', extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a canonical supervisor-command payload for both legacy and typed transports."""
    envelope = SupervisorCommandEnvelope(
        command=str(command or '').strip().lower(),
        target_mode=str(target_mode or '').strip().upper(),
        reason=str(reason or ''),
        source=str(source or ''),
        payload=extra,
        schema_version=str(schema_version or 'v1'),
    )
    if not envelope.command:
        raise TransportContractError('supervisor command missing command')
    payload = envelope.to_payload()
    payload['command'] = envelope.command
    payload['mode'] = envelope.target_mode
    payload['target_mode'] = envelope.target_mode
    payload['reason'] = envelope.reason
    payload['source'] = envelope.source
    payload['schema_version'] = envelope.schema_version
    return payload


def supervisor_command_payload_json(command: str, *, event_type: str = 'supervisor_command', target_mode: str = '', reason: str = '', source: str = '', schema_version: str = 'v1', extra: Mapping[str, Any] | None = None) -> str:
    """Serialize a canonical supervisor command into the legacy JSON event shape."""
    return serialize_payload(
        event_type,
        supervisor_command_payload(
            command,
            target_mode=target_mode,
            reason=reason,
            source=source,
            schema_version=schema_version,
            extra=extra,
        ),
    )


def populate_supervisor_command_message(message: Any, command: str, *, target_mode: str = '', reason: str = '', source: str = '', schema_version: str = 'v1', event_type: str = 'supervisor_command', extra: Mapping[str, Any] | None = None) -> str:
    """Populate a typed supervisor command message while keeping payload_json aligned."""
    payload = supervisor_command_payload(
        command,
        target_mode=target_mode,
        reason=reason,
        source=source,
        schema_version=schema_version,
        extra=extra,
    )
    payload_json = serialize_payload(event_type, payload)
    setattr(message, 'command', str(payload['command']))
    setattr(message, 'target_mode', str(payload['target_mode']))
    setattr(message, 'reason', str(payload['reason']))
    setattr(message, 'source', str(payload['source']))
    setattr(message, 'schema_version', str(payload['schema_version']))
    if hasattr(message, 'payload_json'):
        setattr(message, 'payload_json', payload_json)
    return payload_json


def supervisor_command_payload_from_message(message: Any, *, default_event_type: str = 'typed_supervisor_command') -> dict[str, Any]:
    """Recover a canonical supervisor-command payload from a typed ROS message."""
    raw_payload_json = getattr(message, 'payload_json', '') or ''
    payload = safe_json_dict(raw_payload_json, fallback={}) if raw_payload_json else {}
    command = str(payload.get('command', getattr(message, 'command', ''))).strip().lower()
    if not command:
        raise TransportContractError('typed supervisor command missing command')
    normalized = supervisor_command_payload(
        command,
        target_mode=str(payload.get('target_mode', payload.get('mode', getattr(message, 'target_mode', ''))) or ''),
        reason=str(payload.get('reason', getattr(message, 'reason', '')) or ''),
        source=str(payload.get('source', getattr(message, 'source', '')) or ''),
        schema_version=str(payload.get('schema_version', getattr(message, 'schema_version', 'v1')) or 'v1'),
        extra={k: v for k, v in payload.items() if k not in {'command', 'mode', 'target_mode', 'reason', 'source', 'schema_version', 'type'}},
    )
    normalized['type'] = str(payload.get('type', default_event_type) or default_event_type)
    return normalized


def diagnostics_payload(node: str, event_type: str, lifecycle_state: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return DiagnosticsEnvelope(node=node, event_type=event_type, lifecycle_state=lifecycle_state, payload=payload).to_payload()


def supervisor_state_payload(node: str, profile_name: str, current_mode: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return SupervisorStateEnvelope(node=node, profile_name=profile_name, current_mode=current_mode, payload=payload).to_payload()


def action_executor_event_payload(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    data = dict(payload or {})
    return ActionExecutorEventEnvelope(
        job_id=str(data.get('jobId', data.get('job_id', ''))),
        kind=str(data.get('kind', '')),
        status=str(data.get('status', '')),
        source=str(data.get('source', '')),
        payload=data,
        schema_version=str(data.get('schema_version', 'v1') or 'v1'),
    ).to_payload()


def control_payload(command: str, *, source: str = '', reason: str = '', batch_id: str = '', item_id: int = -1, trace_id: str = '', schema_version: str = 'v1', extra: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Build a canonical control payload for both legacy and typed transports."""
    envelope = ControlCommandEnvelope(
        command=str(command),
        source=str(source),
        reason=str(reason),
        batch_id=str(batch_id),
        item_id=int(item_id if item_id is not None else -1),
        trace_id=str(trace_id),
        schema_version=str(schema_version or 'v1'),
    )
    payload = envelope.to_payload()
    payload.update(dict(extra or {}))
    payload['command'] = envelope.command
    payload['action'] = envelope.command
    payload['source'] = envelope.source
    payload['reason'] = envelope.reason
    payload['batch_id'] = envelope.batch_id
    payload['item_id'] = envelope.item_id
    payload['trace_id'] = envelope.trace_id
    payload['schema_version'] = envelope.schema_version
    return payload


def control_payload_json(command: str, *, event_type: str = 'control_command', source: str = '', reason: str = '', batch_id: str = '', item_id: int = -1, trace_id: str = '', schema_version: str = 'v1', extra: Mapping[str, Any] | None = None) -> str:
    """Serialize a canonical control payload into the legacy JSON event shape."""
    return serialize_payload(
        event_type,
        control_payload(
            command,
            source=source,
            reason=reason,
            batch_id=batch_id,
            item_id=item_id,
            trace_id=trace_id,
            schema_version=schema_version,
            extra=extra,
        ),
    )


def populate_control_command_message(message: Any, command: str, *, source: str = '', reason: str = '', batch_id: str = '', item_id: int = -1, trace_id: str = '', schema_version: str = 'v1', event_type: str = 'control_command', extra: Mapping[str, Any] | None = None) -> str:
    """Populate a ROS typed control message in one place.

    The helper keeps the typed ``ControlCommand`` schema and the legacy JSON
    payload synchronized. If the caller passes an object without
    ``payload_json``, the helper still fills the stable structural fields.
    """
    payload = control_payload(
        command,
        source=source,
        reason=reason,
        batch_id=batch_id,
        item_id=item_id,
        trace_id=trace_id,
        schema_version=schema_version,
        extra=extra,
    )
    payload_json = serialize_payload(event_type, payload)
    setattr(message, 'command', str(payload['command']))
    setattr(message, 'source', str(payload['source']))
    setattr(message, 'reason', str(payload['reason']))
    setattr(message, 'batch_id', str(payload['batch_id']))
    setattr(message, 'item_id', int(payload['item_id']))
    setattr(message, 'trace_id', str(payload['trace_id']))
    setattr(message, 'schema_version', str(payload['schema_version']))
    if hasattr(message, 'payload_json'):
        setattr(message, 'payload_json', payload_json)
    return payload_json


def control_payload_from_message(message: Any, *, default_event_type: str = 'typed_control_bridge') -> dict[str, Any]:
    """Recover a canonical control payload from a typed ROS message.

    Boundary behavior:
        - If ``payload_json`` exists and decodes to a JSON object, that object is
          used as the primary source and then normalized.
        - If ``payload_json`` is missing or empty, the helper synthesizes a
          legacy-compatible payload from the structural message fields.
    """
    raw_payload_json = getattr(message, 'payload_json', '') or ''
    payload = safe_json_dict(raw_payload_json, fallback={}) if raw_payload_json else {}
    command = str(payload.get('command', payload.get('action', getattr(message, 'command', '')))).strip()
    if not command:
        raise TransportContractError('typed control message missing command/action')
    normalized = control_payload(
        command,
        source=str(payload.get('source', getattr(message, 'source', '')) or ''),
        reason=str(payload.get('reason', getattr(message, 'reason', '')) or ''),
        batch_id=str(payload.get('batch_id', getattr(message, 'batch_id', '')) or ''),
        item_id=int(payload.get('item_id', getattr(message, 'item_id', -1)) or -1),
        trace_id=str(payload.get('trace_id', getattr(message, 'trace_id', '')) or ''),
        schema_version=str(payload.get('schema_version', getattr(message, 'schema_version', 'v1')) or 'v1'),
        extra={k: v for k, v in payload.items() if k not in {'command', 'action', 'source', 'reason', 'batch_id', 'item_id', 'trace_id', 'schema_version', 'type'}},
    )
    normalized['type'] = str(payload.get('type', default_event_type) or default_event_type)
    return normalized
