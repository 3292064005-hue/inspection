from __future__ import annotations

"""Stable transport/control boundary exports for application packages.

This module must remain import-safe in unit-test environments that do not ship
ROS message packages. Control-plane constants are always available; typed/dual
publish helpers fall back to ROS-free implementations when ``std_msgs`` is not
installed.
"""

from types import SimpleNamespace
from typing import Any, Mapping

from .control_protocol import (
    CANCEL_COMMAND,
    ENTER_MANUAL_COMMAND,
    EXIT_MANUAL_COMMAND,
    MANUAL_STEP_CAPTURE_COMMAND,
    MANUAL_STEP_FEED_COMMAND,
    MANUAL_STEP_SORT_COMMAND,
    PAUSE_COMMAND,
    RESET_COMMAND,
    RESUME_COMMAND,
    START_COMMAND,
    STOP_COMMAND,
    extract_control_command,
    normalize_control_command,
)
from .transport_boundary import legacy_publish_enabled, typed_publish_enabled
from .transport_contracts import (
    ACTION_EXECUTOR_EVENT_TOPIC_TYPED,
    CAPTURE_REQUEST_TOPIC_TYPED,
    CONTROL_TOPIC_TYPED,
    DIAGNOSTICS_TOPIC_TYPED,
    SUPERVISOR_COMMAND_TOPIC_TYPED,
    SUPERVISOR_STATE_TOPIC_TYPED,
    action_executor_event_payload,
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
from .logging_tools import safe_json_loads


def _legacy_string(payload_json: str) -> Any:
    return SimpleNamespace(data=str(payload_json))


try:  # pragma: no cover - exercised in ROS-enabled environments
    from .transport_adapters import (
        legacy_payload_json_from_typed_message,
        normalized_payload_from_typed_message,
        publish_dual_capture_request,
        publish_dual_control,
        publish_dual_supervisor_command,
        publish_dual_supervisor_state,
    )
except ModuleNotFoundError:  # pragma: no cover - ROS-free unit-test fallback

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
            legacy_publisher.publish(_legacy_string(payload_json))
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
            legacy_publisher.publish(_legacy_string(payload_json))
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
            legacy_publisher.publish(_legacy_string(payload_json))
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
        normalized = supervisor_state_payload(node_name, profile_name, current_mode, payload)
        payload_json = serialize_payload(event_type, normalized)
        if legacy_publish_enabled('supervisor_state'):
            legacy_publisher.publish(_legacy_string(payload_json))
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


__all__ = [
    'ACTION_EXECUTOR_EVENT_TOPIC_TYPED',
    'CAPTURE_REQUEST_TOPIC_TYPED',
    'CANCEL_COMMAND',
    'CONTROL_TOPIC_TYPED',
    'DIAGNOSTICS_TOPIC_TYPED',
    'ENTER_MANUAL_COMMAND',
    'EXIT_MANUAL_COMMAND',
    'MANUAL_STEP_CAPTURE_COMMAND',
    'MANUAL_STEP_FEED_COMMAND',
    'MANUAL_STEP_SORT_COMMAND',
    'PAUSE_COMMAND',
    'RESET_COMMAND',
    'RESUME_COMMAND',
    'START_COMMAND',
    'STOP_COMMAND',
    'SUPERVISOR_COMMAND_TOPIC_TYPED',
    'SUPERVISOR_STATE_TOPIC_TYPED',
    'action_executor_event_payload',
    'capture_request_payload_from_message',
    'diagnostics_payload',
    'extract_control_command',
    'legacy_payload_json_from_typed_message',
    'normalize_control_command',
    'normalized_payload_from_typed_message',
    'publish_dual_capture_request',
    'publish_dual_control',
    'publish_dual_supervisor_command',
    'publish_dual_supervisor_state',
    'serialize_payload',
    'supervisor_command_payload_from_message',
]
