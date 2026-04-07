from __future__ import annotations

"""Boundary adapters for legacy/typed ROS transport coexistence.

The migration period still requires selected topics to be published on both the
legacy JSON ``std_msgs/String`` channels and the newer typed message channels.
This module keeps the dual-publish and typed-to-legacy bridge behavior in one
place so business nodes do not each reinvent slightly different wiring.
"""

from typing import Any, Mapping

from std_msgs.msg import String

from .logging_tools import safe_json_loads
from .transport_contracts import (
    capture_request_payload_from_message,
    capture_request_payload_json,
    control_payload_from_message,
    control_payload_json,
    diagnostics_payload,
    populate_capture_request_message,
    populate_control_command_message,
    serialize_payload,
    supervisor_state_payload,
)


def publish_dual_control(
    *,
    legacy_publisher: Any,
    typed_publisher: Any | None,
    typed_message_cls: type[Any] | None,
    command: str,
    source: str,
    event_type: str,
    reason: str = '',
    batch_id: str = '',
    item_id: int = -1,
    trace_id: str = '',
    schema_version: str = 'v1',
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Publish one canonical control command to both legacy and typed topics."""
    payload_json = control_payload_json(
        command,
        event_type=event_type,
        source=source,
        reason=reason,
        batch_id=batch_id,
        item_id=item_id,
        trace_id=trace_id,
        schema_version=schema_version,
        extra=extra,
    )
    legacy = String()
    legacy.data = payload_json
    legacy_publisher.publish(legacy)
    if typed_publisher is not None and typed_message_cls is not None:
        typed = typed_message_cls()
        populate_control_command_message(
            typed,
            command,
            source=source,
            event_type=event_type,
            reason=reason,
            batch_id=batch_id,
            item_id=item_id,
            trace_id=trace_id,
            schema_version=schema_version,
            extra=extra,
        )
        typed_publisher.publish(typed)
    return payload_json


def publish_dual_capture_request(
    *,
    legacy_publisher: Any,
    typed_publisher: Any | None,
    typed_message_cls: type[Any] | None,
    trace_id: str,
    source: str,
    event_type: str = 'capture_request',
    batch_id: str = '',
    item_id: int = -1,
    frame_index: int = -1,
    schema_version: str = 'v1',
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Publish one canonical capture request to both legacy and typed topics."""
    payload_json = capture_request_payload_json(
        trace_id,
        event_type=event_type,
        batch_id=batch_id,
        item_id=item_id,
        frame_index=frame_index,
        source=source,
        schema_version=schema_version,
        extra=extra,
    )
    legacy = String()
    legacy.data = payload_json
    legacy_publisher.publish(legacy)
    if typed_publisher is not None and typed_message_cls is not None:
        typed = typed_message_cls()
        populate_capture_request_message(
            typed,
            trace_id,
            event_type=event_type,
            batch_id=batch_id,
            item_id=item_id,
            frame_index=frame_index,
            source=source,
            schema_version=schema_version,
            extra=extra,
        )
        typed_publisher.publish(typed)
    return payload_json


def publish_dual_diagnostics_snapshot(
    *,
    legacy_publisher: Any,
    typed_publisher: Any | None,
    typed_message_cls: type[Any] | None,
    node_name: str,
    event_type: str,
    lifecycle_state: str,
    payload: Mapping[str, Any] | None = None,
) -> str:
    """Publish diagnostics payloads on both legacy and typed topics."""
    normalized = diagnostics_payload(node_name, event_type, lifecycle_state, payload)
    payload_json = serialize_payload(event_type, normalized)
    legacy = String(); legacy.data = payload_json; legacy_publisher.publish(legacy)
    if typed_publisher is not None and typed_message_cls is not None:
        typed = typed_message_cls()
        typed.node = node_name
        typed.event_type = event_type
        typed.lifecycle_state = lifecycle_state
        typed.schema_version = str(normalized.get('schema_version', 'v1') or 'v1')
        typed.payload_json = payload_json
        typed_publisher.publish(typed)
    return payload_json


def publish_dual_supervisor_state(
    *,
    legacy_publisher: Any,
    typed_publisher: Any | None,
    typed_message_cls: type[Any] | None,
    node_name: str,
    profile_name: str,
    current_mode: str,
    payload: Mapping[str, Any] | None = None,
    event_type: str = 'supervisor_state',
) -> str:
    """Publish supervisor state on both legacy and typed topics."""
    normalized = supervisor_state_payload(node_name, profile_name, current_mode, payload)
    payload_json = serialize_payload(event_type, normalized)
    legacy = String(); legacy.data = payload_json; legacy_publisher.publish(legacy)
    if typed_publisher is not None and typed_message_cls is not None:
        typed = typed_message_cls()
        typed.node = node_name
        typed.profile_name = profile_name
        typed.current_mode = current_mode
        typed.schema_version = str(normalized.get('schema_version', 'v1') or 'v1')
        typed.payload_json = payload_json
        typed_publisher.publish(typed)
    return payload_json


def legacy_payload_json_from_typed_message(message: Any, *, default_event_type: str, fallback: Mapping[str, Any] | None = None) -> str:
    """Recover a stable legacy JSON payload from a typed message.

    Args:
        message: Incoming typed ROS message.
        default_event_type: Event type used when the message does not already
            carry a ``type`` field.
        fallback: Optional structural fallback payload used when the typed
            message class does not provide a dedicated contract helper.

    Returns:
        Legacy JSON event payload.

    Raises:
        ValueError: When the message cannot be normalized into a JSON object.

    Boundary behavior:
        The helper prefers explicit ``payload_json`` when present. For control
        and capture request messages it synthesizes a canonical legacy payload
        from structural fields when the raw JSON body is absent.
    """

    payload_json = getattr(message, 'payload_json', '') or ''
    if payload_json:
        decoded = safe_json_loads(payload_json, {})
        if isinstance(decoded, dict):
            decoded.setdefault('type', str(decoded.get('type', default_event_type) or default_event_type))
            return serialize_payload(str(decoded.get('type', default_event_type)), decoded)
    if all(hasattr(message, field) for field in ('command', 'source', 'reason', 'batch_id', 'item_id', 'trace_id')):
        payload = control_payload_from_message(message, default_event_type=default_event_type)
        return serialize_payload(str(payload.get('type', default_event_type)), payload)
    if all(hasattr(message, field) for field in ('trace_id', 'batch_id', 'item_id', 'frame_index', 'source')):
        payload = capture_request_payload_from_message(message, default_event_type=default_event_type)
        return serialize_payload(str(payload.get('type', default_event_type)), payload)
    decoded_fallback = dict(fallback or {})
    decoded_fallback.setdefault('type', default_event_type)
    return serialize_payload(str(decoded_fallback.get('type', default_event_type)), decoded_fallback)
