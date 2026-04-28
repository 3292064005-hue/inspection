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
from .transport_boundary import legacy_publish_enabled, typed_publish_enabled
from .transport_contracts import (
    capture_request_payload_from_message,
    capture_request_payload_json,
    control_payload_from_message,
    control_payload_json,
    diagnostics_payload,
    populate_capture_request_message,
    populate_control_command_message,
    populate_supervisor_command_message,
    serialize_payload,
    supervisor_command_payload_from_message,
    supervisor_command_payload_json,
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
    if legacy_publish_enabled('control'):
        legacy = String()
        legacy.data = payload_json
        legacy_publisher.publish(legacy)
    if typed_publish_enabled('control') and typed_publisher is not None and typed_message_cls is not None:
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
    if legacy_publish_enabled('capture_request'):
        legacy = String()
        legacy.data = payload_json
        legacy_publisher.publish(legacy)
    if typed_publish_enabled('capture_request') and typed_publisher is not None and typed_message_cls is not None:
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
    if legacy_publish_enabled('diagnostics'):
        legacy = String(); legacy.data = payload_json; legacy_publisher.publish(legacy)
    if typed_publish_enabled('diagnostics') and typed_publisher is not None and typed_message_cls is not None:
        typed = typed_message_cls()
        typed.node = node_name
        typed.event_type = event_type
        typed.lifecycle_state = lifecycle_state
        typed.schema_version = str(normalized.get('schema_version', 'v1') or 'v1')
        typed.payload_json = payload_json
        typed_publisher.publish(typed)
    return payload_json


def publish_dual_supervisor_command(
    *,
    legacy_publisher: Any,
    typed_publisher: Any | None,
    typed_message_cls: type[Any] | None,
    command: str,
    target_mode: str = '',
    source: str = '',
    event_type: str = 'supervisor_command',
    reason: str = '',
    schema_version: str = 'v1',
    extra: Mapping[str, Any] | None = None,
) -> str:
    """Publish one canonical supervisor command to both legacy and typed topics."""
    payload_json = supervisor_command_payload_json(
        command,
        event_type=event_type,
        target_mode=target_mode,
        reason=reason,
        source=source,
        schema_version=schema_version,
        extra=extra,
    )
    if legacy_publish_enabled('supervisor_command'):
        legacy = String()
        legacy.data = payload_json
        legacy_publisher.publish(legacy)
    if typed_publish_enabled('supervisor_command') and typed_publisher is not None and typed_message_cls is not None:
        typed = typed_message_cls()
        populate_supervisor_command_message(
            typed,
            command,
            target_mode=target_mode,
            reason=reason,
            source=source,
            schema_version=schema_version,
            event_type=event_type,
            extra=extra,
        )
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
    if legacy_publish_enabled('supervisor_state'):
        legacy = String(); legacy.data = payload_json; legacy_publisher.publish(legacy)
    if typed_publish_enabled('supervisor_state') and typed_publisher is not None and typed_message_cls is not None:
        typed = typed_message_cls()
        typed.node = node_name
        typed.profile_name = profile_name
        typed.current_mode = current_mode
        typed.schema_version = str(normalized.get('schema_version', 'v1') or 'v1')
        typed.payload_json = payload_json
        typed_publisher.publish(typed)
    return payload_json


def normalized_payload_from_typed_message(message: Any, *, default_event_type: str, fallback: Mapping[str, Any] | None = None, bridge_name: str = '') -> dict[str, Any]:
    """Normalize a typed message into one canonical dict payload.

    Args:
        message: Incoming typed ROS message.
        default_event_type: Event type used when the message payload does not
            already declare ``type``.
        fallback: Optional structural fallback payload.
        bridge_name: Logical bridge identifier used to select the correct
            canonical reconstruction strategy during migration.

    Returns:
        Canonical payload dictionary.

    Raises:
        ValueError: When the typed message cannot be normalized.

    Boundary behavior:
        The helper prefers explicit ``payload_json`` when present. When the raw
        JSON body is absent it reconstructs one canonical payload directly from
        the typed fields instead of forcing callers through a legacy ``String``
        bridge first.
    """

    payload_json = getattr(message, 'payload_json', '') or ''
    if payload_json:
        decoded = safe_json_loads(payload_json, {})
        if isinstance(decoded, dict):
            decoded.setdefault('type', str(decoded.get('type', default_event_type) or default_event_type))
            return decoded
    if bridge_name == 'control' or all(hasattr(message, field) for field in ('command', 'source', 'reason', 'batch_id', 'item_id', 'trace_id')):
        return control_payload_from_message(message, default_event_type=default_event_type)
    if bridge_name == 'capture_request' or all(hasattr(message, field) for field in ('trace_id', 'batch_id', 'item_id', 'frame_index', 'source')):
        return capture_request_payload_from_message(message, default_event_type=default_event_type)
    if bridge_name == 'supervisor_command' or all(hasattr(message, field) for field in ('command', 'target_mode', 'reason', 'source')):
        return supervisor_command_payload_from_message(message, default_event_type=default_event_type)
    if bridge_name == 'diagnostics':
        payload = dict(fallback or {})
        payload.setdefault('type', default_event_type)
        payload.setdefault('node', str(getattr(message, 'node', getattr(message, 'node_name', '')) or ''))
        payload.setdefault('status', str(getattr(message, 'status', getattr(message, 'lifecycle_state', '')) or ''))
        return payload
    if bridge_name == 'supervisor_state':
        payload = dict(fallback or {})
        payload.setdefault('type', default_event_type)
        payload.setdefault('node', str(getattr(message, 'node', '') or ''))
        payload.setdefault('profile_name', str(getattr(message, 'profile_name', '') or ''))
        payload.setdefault('current_mode', str(getattr(message, 'current_mode', '') or ''))
        return payload
    decoded_fallback = dict(fallback or {})
    decoded_fallback.setdefault('type', default_event_type)
    return decoded_fallback


def legacy_payload_json_from_typed_message(message: Any, *, default_event_type: str, fallback: Mapping[str, Any] | None = None, bridge_name: str = '') -> str:
    payload = normalized_payload_from_typed_message(message, default_event_type=default_event_type, fallback=fallback, bridge_name=bridge_name)
    return serialize_payload(str(payload.get('type', default_event_type)), payload)
