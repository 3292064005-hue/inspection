from __future__ import annotations

"""Typed runtime-event contracts for the station execution backbone.

The migration keeps legacy ``/inspection/events`` available as an optional
compatibility bridge, but the canonical transport for critical runtime events is
now a dedicated typed topic per event kind. Each typed message still carries a
``payload_json`` field so legacy consumers, recordings, and tests can recover
one canonical envelope without duplicating normalization logic.
"""

from collections import OrderedDict
from typing import Any, Callable, Mapping
import json
import time

from .logging_common import event_to_json, safe_json_loads
from .transport_boundary import legacy_publish_enabled, typed_publish_enabled

try:
    from std_msgs.msg import String
except Exception:  # pragma: no cover - ROS-free unit-test fallback
    class String:  # type: ignore[override]
        def __init__(self) -> None:
            self.data = ''


class RuntimeEventDeduper:
    """TTL-bounded de-duplication guard for dual-transport runtime events.

    During migration a consumer may observe the same canonical runtime event via
    the legacy JSON topic and the typed topic. This helper suppresses the second
    observation within a short time window so rollback windows do not double
    mutate state, log traces, or inflate diagnostics.
    """

    def __init__(self, *, max_entries: int = 512, ttl_sec: float = 2.0) -> None:
        self.max_entries = max(1, int(max_entries))
        self.ttl_sec = max(0.1, float(ttl_sec))
        self._items: OrderedDict[str, float] = OrderedDict()

    def seen_recently(self, payload: Mapping[str, Any] | None) -> bool:
        signature = runtime_event_signature(payload)
        if not signature:
            return False
        now = time.monotonic()
        self.prune(now=now)
        if signature in self._items:
            self._items[signature] = now
            return True
        self._items[signature] = now
        while len(self._items) > self.max_entries:
            self._items.popitem(last=False)
        return False

    def prune(self, *, now: float | None = None) -> None:
        deadline = (time.monotonic() if now is None else now) - self.ttl_sec
        stale = [signature for signature, seen_at in self._items.items() if seen_at < deadline]
        for signature in stale:
            self._items.pop(signature, None)


def runtime_event_signature(payload: Mapping[str, Any] | None) -> str:
    if not isinstance(payload, Mapping):
        return ''
    event_type = str(payload.get('type', '') or '').strip().lower()
    if event_type not in _RUNTIME_EVENT_DEFAULTS:
        return ''
    canonical = runtime_event_payload(event_type, payload)
    try:
        return json.dumps(canonical, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':'))
    except Exception:
        return ''


def is_runtime_event_payload(payload: Mapping[str, Any] | None) -> bool:
    if not isinstance(payload, Mapping):
        return False
    return str(payload.get('type', '') or '').strip().lower() in _RUNTIME_EVENT_DEFAULTS


FSM_TRANSITION_TOPIC_TYPED = '/inspection/events/fsm_transition_typed'
VISION_FRAME_ACQUIRED_TOPIC_TYPED = '/inspection/events/vision_frame_acquired_typed'
DECISION_PUBLISHED_TOPIC_TYPED = '/inspection/events/decision_published_typed'
BRIDGE_HEARTBEAT_TOPIC_TYPED = '/inspection/events/bridge_heartbeat_typed'
BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED = '/inspection/events/bridge_handshake_complete_typed'
FAULT_RAISED_TOPIC_TYPED = '/inspection/events/fault_raised_typed'

_RUNTIME_EVENT_DEFAULTS: dict[str, dict[str, Any]] = {
    'fsm_transition': {
        'bridge_name': 'fsm_transition',
        'topic': FSM_TRANSITION_TOPIC_TYPED,
        'required_fields': ('from_phase', 'to_phase', 'event', 'reason', 'item_id', 'batch_id', 'trace_id', 'cycle_index', 'runtime_phase', 'profile_name', 'phase_elapsed_ms'),
    },
    'vision_frame_acquired': {
        'bridge_name': 'vision_frame_acquired',
        'topic': VISION_FRAME_ACQUIRED_TOPIC_TYPED,
        'required_fields': ('trace_id', 'batch_id', 'item_id', 'frame_index', 'lifecycle_state'),
    },
    'decision_published': {
        'bridge_name': 'decision_published',
        'topic': DECISION_PUBLISHED_TOPIC_TYPED,
        'required_fields': ('output_topic', 'item_id', 'batch_id', 'trace_id', 'decision', 'action_code', 'target_bin', 'matched_rule_id', 'matched_rule_priority', 'confidence', 'severity'),
    },
    'bridge_heartbeat': {
        'bridge_name': 'bridge_heartbeat',
        'topic': BRIDGE_HEARTBEAT_TOPIC_TYPED,
        'required_fields': ('seq', 'batch_id', 'item_id', 'trace_id', 'detail_json'),
    },
    'bridge_handshake_complete': {
        'bridge_name': 'bridge_handshake_complete',
        'topic': BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED,
        'required_fields': ('batch_id', 'item_id', 'trace_id', 'capabilities_json'),
    },
    'fault_raised': {
        'bridge_name': 'fault_raised',
        'topic': FAULT_RAISED_TOPIC_TYPED,
        'required_fields': ('code', 'description', 'item_id', 'batch_id', 'trace_id', 'cycle_index', 'runtime_phase', 'profile_name'),
    },
}


def runtime_event_policy_name(event_type: str) -> str:
    normalized = str(event_type or '').strip().lower()
    spec = _RUNTIME_EVENT_DEFAULTS.get(normalized, {})
    return str(spec.get('bridge_name', normalized or 'runtime_event'))


def runtime_event_topic(event_type: str) -> str:
    normalized = str(event_type or '').strip().lower()
    spec = _RUNTIME_EVENT_DEFAULTS.get(normalized, {})
    return str(spec.get('topic', ''))


def runtime_event_catalog() -> dict[str, dict[str, Any]]:
    return {name: dict(spec) for name, spec in _RUNTIME_EVENT_DEFAULTS.items()}


def runtime_event_payload(event_type: str, payload: Mapping[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    normalized_type = str(event_type or '').strip() or 'runtime_event'
    merged = dict(payload or {})
    merged.update(extra)
    merged['type'] = normalized_type
    merged.setdefault('schema_version', 'v1')
    return merged


def runtime_event_payload_json(event_type: str, payload: Mapping[str, Any] | None = None, **extra: Any) -> str:
    normalized = runtime_event_payload(event_type, payload, **extra)
    return event_to_json(str(normalized.get('type', event_type) or event_type), **{k: v for k, v in normalized.items() if k != 'type'})


def normalize_runtime_event_message(message: Any, *, default_event_type: str) -> dict[str, Any]:
    """Recover one canonical runtime-event payload from a typed message.

    Args:
        message: Typed runtime-event message instance.
        default_event_type: Event type to inject when payload_json is absent.

    Returns:
        Canonical JSON-shaped runtime-event payload.

    Raises:
        ValueError: When the payload cannot be reconstructed into a mapping.

    Boundary behavior:
        ``payload_json`` remains the source of truth during migration. Field-wise
        fallback reconstruction exists only so test doubles and partially filled
        typed messages remain readable.
    """
    payload_json = str(getattr(message, 'payload_json', '') or '').strip()
    if payload_json:
        decoded = safe_json_loads(payload_json, {})
        if isinstance(decoded, dict):
            decoded.setdefault('type', default_event_type)
            decoded.setdefault('schema_version', str(getattr(message, 'schema_version', decoded.get('schema_version', 'v1')) or 'v1'))
            return decoded
    payload: dict[str, Any] = {'type': default_event_type, 'schema_version': str(getattr(message, 'schema_version', 'v1') or 'v1')}
    spec = _RUNTIME_EVENT_DEFAULTS.get(default_event_type, {})
    for field in spec.get('required_fields', ()):  # pragma: no branch - fixed registry
        value = getattr(message, field, None)
        if field in {'detail_json', 'capabilities_json'}:
            payload[field[:-5] if field.endswith('_json') else field] = safe_json_loads(value, {}) if value else {}
            continue
        payload[field] = value
    if default_event_type == 'bridge_heartbeat' and 'detail' not in payload:
        payload['detail'] = safe_json_loads(str(getattr(message, 'detail_json', '') or '{}'), {})
    if default_event_type == 'bridge_handshake_complete' and 'capabilities' not in payload:
        payload['capabilities'] = safe_json_loads(str(getattr(message, 'capabilities_json', '') or '{}'), {})
    return payload


def populate_fsm_transition_message(message: Any, payload: Mapping[str, Any]) -> str:
    normalized = runtime_event_payload('fsm_transition', payload)
    message.from_phase = str(normalized.get('from_phase', '') or '')
    message.to_phase = str(normalized.get('to_phase', '') or '')
    message.event = str(normalized.get('event', '') or '')
    message.reason = str(normalized.get('reason', '') or '')
    message.phase_elapsed_ms = float(normalized.get('phase_elapsed_ms', 0.0) or 0.0)
    message.item_id = int(normalized.get('item_id', -1) or -1)
    message.batch_id = str(normalized.get('batch_id', '') or '')
    message.trace_id = str(normalized.get('trace_id', '') or '')
    message.cycle_index = int(normalized.get('cycle_index', -1) or -1)
    message.runtime_phase = str(normalized.get('runtime_phase', '') or '')
    message.profile_name = str(normalized.get('profile_name', '') or '')
    message.schema_version = str(normalized.get('schema_version', 'v1') or 'v1')
    message.payload_json = runtime_event_payload_json('fsm_transition', normalized)
    return message.payload_json


def populate_vision_frame_acquired_message(message: Any, payload: Mapping[str, Any]) -> str:
    normalized = runtime_event_payload('vision_frame_acquired', payload)
    message.trace_id = str(normalized.get('trace_id', '') or '')
    message.batch_id = str(normalized.get('batch_id', '') or '')
    message.item_id = int(normalized.get('item_id', -1) or -1)
    message.frame_index = int(normalized.get('frame_index', -1) or -1)
    message.lifecycle_state = str(normalized.get('lifecycle_state', '') or '')
    message.schema_version = str(normalized.get('schema_version', 'v1') or 'v1')
    message.payload_json = runtime_event_payload_json('vision_frame_acquired', normalized)
    return message.payload_json


def populate_decision_published_message(message: Any, payload: Mapping[str, Any]) -> str:
    normalized = runtime_event_payload('decision_published', payload)
    message.output_topic = str(normalized.get('output_topic', '') or '')
    message.item_id = int(normalized.get('item_id', -1) or -1)
    message.batch_id = str(normalized.get('batch_id', '') or '')
    message.trace_id = str(normalized.get('trace_id', '') or '')
    message.decision = str(normalized.get('decision', '') or '')
    message.action_code = int(normalized.get('action_code', 0) or 0)
    message.target_bin = str(normalized.get('target_bin', '') or '')
    message.matched_rule_id = str(normalized.get('matched_rule_id', '') or '')
    message.matched_rule_priority = int(normalized.get('matched_rule_priority', 0) or 0)
    message.confidence = float(normalized.get('confidence', 0.0) or 0.0)
    message.severity = str(normalized.get('severity', '') or '')
    message.schema_version = str(normalized.get('schema_version', 'v1') or 'v1')
    message.payload_json = runtime_event_payload_json('decision_published', normalized)
    return message.payload_json


def populate_bridge_heartbeat_message(message: Any, payload: Mapping[str, Any]) -> str:
    normalized = runtime_event_payload('bridge_heartbeat', payload)
    detail_json = json.dumps(normalized.get('detail', {}), ensure_ascii=False, sort_keys=True)
    message.seq = int(normalized.get('seq', 0) or 0)
    message.batch_id = str(normalized.get('batch_id', '') or '')
    message.item_id = int(normalized.get('item_id', -1) or -1)
    message.trace_id = str(normalized.get('trace_id', '') or '')
    message.detail_json = detail_json
    message.schema_version = str(normalized.get('schema_version', 'v1') or 'v1')
    normalized = dict(normalized)
    normalized['detail'] = safe_json_loads(detail_json, {})
    message.payload_json = runtime_event_payload_json('bridge_heartbeat', normalized)
    return message.payload_json


def populate_bridge_handshake_complete_message(message: Any, payload: Mapping[str, Any]) -> str:
    normalized = runtime_event_payload('bridge_handshake_complete', payload)
    capabilities_json = json.dumps(normalized.get('capabilities', {}), ensure_ascii=False, sort_keys=True)
    message.batch_id = str(normalized.get('batch_id', '') or '')
    message.item_id = int(normalized.get('item_id', -1) or -1)
    message.trace_id = str(normalized.get('trace_id', '') or '')
    message.capabilities_json = capabilities_json
    message.schema_version = str(normalized.get('schema_version', 'v1') or 'v1')
    normalized = dict(normalized)
    normalized['capabilities'] = safe_json_loads(capabilities_json, {})
    message.payload_json = runtime_event_payload_json('bridge_handshake_complete', normalized)
    return message.payload_json


def populate_fault_raised_message(message: Any, payload: Mapping[str, Any]) -> str:
    normalized = runtime_event_payload('fault_raised', payload)
    message.code = str(normalized.get('code', '') or '')
    message.description = str(normalized.get('description', '') or '')
    message.item_id = int(normalized.get('item_id', -1) or -1)
    message.batch_id = str(normalized.get('batch_id', '') or '')
    message.trace_id = str(normalized.get('trace_id', '') or '')
    message.cycle_index = int(normalized.get('cycle_index', -1) or -1)
    message.runtime_phase = str(normalized.get('runtime_phase', '') or '')
    message.profile_name = str(normalized.get('profile_name', '') or '')
    message.schema_version = str(normalized.get('schema_version', 'v1') or 'v1')
    message.payload_json = runtime_event_payload_json('fault_raised', normalized)
    return message.payload_json


def publish_dual_runtime_event(
    *,
    event_type: str,
    legacy_publisher: Any,
    typed_publisher: Any | None,
    typed_message_cls: type[Any] | None,
    populate_message: Callable[[Any, Mapping[str, Any]], str] | None,
    payload: Mapping[str, Any],
) -> str:
    """Publish one canonical runtime event to the configured legacy/typed bridges."""
    normalized_type = str(event_type or '').strip().lower()
    bridge_name = runtime_event_policy_name(normalized_type)
    payload_json = runtime_event_payload_json(normalized_type, payload)
    if legacy_publish_enabled(bridge_name):
        legacy_msg = String()
        legacy_msg.data = payload_json
        legacy_publisher.publish(legacy_msg)
    if typed_publish_enabled(bridge_name) and typed_publisher is not None and typed_message_cls is not None and callable(populate_message):
        typed_msg = typed_message_cls()
        populate_message(typed_msg, payload)
        typed_publisher.publish(typed_msg)
    return payload_json
