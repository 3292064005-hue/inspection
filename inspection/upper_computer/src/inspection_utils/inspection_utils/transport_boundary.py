from __future__ import annotations

"""Govern typed-first transport bridging at the ROS boundary.

Business-domain nodes should reason about one canonical transport contract.
Legacy JSON channels now default to disabled and can only be re-enabled through
explicit compatibility environment overrides during rollback windows.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .config import load_yaml
from .io_common import resolve_runtime_path

DEFAULT_TRANSPORT_BRIDGE_POLICY_PATH = 'config/system/transport_bridge_policy.yaml'


@dataclass(frozen=True, slots=True)
class TransportBridgePolicy:
    name: str
    boundary: str = 'edge_bridge'
    core_transport: str = 'typed'
    legacy_publish_enabled: bool = False
    typed_publish_enabled: bool = True
    deprecation_phase: str = 'sunset_planned'
    sunset_release: str = '2026.Q4'
    telemetry_enabled: bool = True
    zero_usage_removal_after_releases: int = 2
    removal_candidate_when_zero_usage: bool = True
    removal_candidate: bool = False
    release_note_required: bool = True
    rollback_strategy: str = 'tagged_release_hotfix_only'
    documentation_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            'name': self.name,
            'boundary': self.boundary,
            'coreTransport': self.core_transport,
            'legacyPublishEnabled': self.legacy_publish_enabled,
            'typedPublishEnabled': self.typed_publish_enabled,
            'deprecationPhase': self.deprecation_phase,
            'sunsetRelease': self.sunset_release,
            'legacyTelemetryEnabled': self.telemetry_enabled,
            'zeroUsageRemovalAfterReleases': self.zero_usage_removal_after_releases,
            'removalCandidateWhenZeroUsage': self.removal_candidate_when_zero_usage,
            'removalCandidate': self.removal_candidate,
            'releaseNoteRequired': self.release_note_required,
            'rollbackStrategy': self.rollback_strategy,
            'documentationRefs': list(self.documentation_refs),
        }


_DEFAULT_POLICIES: dict[str, TransportBridgePolicy] = {
    name: TransportBridgePolicy(name=name)
    for name in (
        'control',
        'capture_request',
        'diagnostics',
        'supervisor_command',
        'supervisor_state',
        'action_executor_event',
        'fsm_transition',
        'vision_frame_acquired',
        'decision_published',
        'bridge_heartbeat',
        'bridge_handshake_complete',
        'fault_raised',
    )
}


def _env_flag(raw: str, default: bool) -> bool:
    if raw == '':
        return bool(default)
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def _legacy_env_override(name: str, configured: bool) -> bool:
    key = str(name or '').strip().upper()
    channel = os.environ.get(f'INSPECTION_TRANSPORT_LEGACY_{key}_ENABLED', '')
    global_flag = os.environ.get('INSPECTION_TRANSPORT_LEGACY_ENABLED', '')
    raw = channel if channel != '' else global_flag
    return _env_flag(raw, configured)


def _typed_env_override(name: str, configured: bool) -> bool:
    key = str(name or '').strip().upper()
    channel = os.environ.get(f'INSPECTION_TRANSPORT_TYPED_{key}_ENABLED', '')
    global_flag = os.environ.get('INSPECTION_TRANSPORT_TYPED_ENABLED', '')
    raw = channel if channel != '' else global_flag
    return _env_flag(raw, configured)


def _apply_env_overrides(policy: TransportBridgePolicy) -> TransportBridgePolicy:
    return TransportBridgePolicy(
        name=policy.name,
        boundary=policy.boundary,
        core_transport=policy.core_transport,
        legacy_publish_enabled=_legacy_env_override(policy.name, policy.legacy_publish_enabled),
        typed_publish_enabled=_typed_env_override(policy.name, policy.typed_publish_enabled),
        deprecation_phase=policy.deprecation_phase,
        sunset_release=policy.sunset_release,
        telemetry_enabled=policy.telemetry_enabled,
        zero_usage_removal_after_releases=policy.zero_usage_removal_after_releases,
        removal_candidate_when_zero_usage=policy.removal_candidate_when_zero_usage,
        removal_candidate=policy.removal_candidate,
        release_note_required=policy.release_note_required,
        rollback_strategy=policy.rollback_strategy,
        documentation_refs=policy.documentation_refs,
    )


def _policy_from_mapping(name: str, payload: dict[str, Any], current: TransportBridgePolicy) -> TransportBridgePolicy:
    return TransportBridgePolicy(
        name=name,
        boundary=str(payload.get('boundary', current.boundary) or current.boundary),
        core_transport=str(payload.get('core_transport', payload.get('coreTransport', current.core_transport)) or current.core_transport),
        legacy_publish_enabled=bool(payload.get('legacy_publish_enabled', payload.get('legacyPublishEnabled', current.legacy_publish_enabled))),
        typed_publish_enabled=bool(payload.get('typed_publish_enabled', payload.get('typedPublishEnabled', current.typed_publish_enabled))),
        deprecation_phase=str(payload.get('deprecation_phase', payload.get('deprecationPhase', current.deprecation_phase)) or current.deprecation_phase),
        sunset_release=str(payload.get('sunset_release', payload.get('sunsetRelease', current.sunset_release)) or current.sunset_release),
        telemetry_enabled=bool(payload.get('legacy_telemetry_enabled', payload.get('legacyTelemetryEnabled', current.telemetry_enabled))),
        zero_usage_removal_after_releases=max(1, int(payload.get('zero_usage_removal_after_releases', payload.get('zeroUsageRemovalAfterReleases', current.zero_usage_removal_after_releases)) or current.zero_usage_removal_after_releases)),
        removal_candidate_when_zero_usage=bool(payload.get('removal_candidate_when_zero_usage', payload.get('removalCandidateWhenZeroUsage', current.removal_candidate_when_zero_usage))),
        removal_candidate=bool(payload.get('removal_candidate', payload.get('removalCandidate', current.removal_candidate))),
        release_note_required=bool(payload.get('release_note_required', payload.get('releaseNoteRequired', current.release_note_required))),
        rollback_strategy=str(payload.get('rollback_strategy', payload.get('rollbackStrategy', current.rollback_strategy)) or current.rollback_strategy),
        documentation_refs=tuple(str(item) for item in payload.get('documentation_refs', payload.get('documentationRefs', current.documentation_refs)) if str(item).strip()),
    )


def transport_bridge_policy_catalog() -> dict[str, TransportBridgePolicy]:
    resolved = resolve_runtime_path(DEFAULT_TRANSPORT_BRIDGE_POLICY_PATH, start=__file__)
    if not resolved.exists():
        return {name: _apply_env_overrides(policy) for name, policy in _DEFAULT_POLICIES.items()}
    payload = load_yaml(resolved) or {}
    bridges = payload.get('bridges', payload) if isinstance(payload, dict) else {}
    if not isinstance(bridges, dict):
        return {name: _apply_env_overrides(policy) for name, policy in _DEFAULT_POLICIES.items()}
    catalog = dict(_DEFAULT_POLICIES)
    for name, current in _DEFAULT_POLICIES.items():
        raw = bridges.get(name, {})
        if isinstance(raw, dict):
            catalog[name] = _apply_env_overrides(_policy_from_mapping(name, raw, current))
        else:
            catalog[name] = _apply_env_overrides(current)
    return catalog


def transport_bridge_policy(name: str) -> TransportBridgePolicy:
    normalized = str(name or '').strip()
    return transport_bridge_policy_catalog().get(normalized, _apply_env_overrides(TransportBridgePolicy(name=normalized or 'unknown')))


def legacy_publish_enabled(name: str) -> bool:
    """Return whether a legacy bridge may publish and record usage when enabled."""
    enabled = transport_bridge_policy(name).legacy_publish_enabled
    if enabled:
        record_legacy_transport_usage(name)
    return enabled


def typed_publish_enabled(name: str) -> bool:
    return transport_bridge_policy(name).typed_publish_enabled


def transport_bridge_matrix() -> list[dict[str, object]]:
    return [policy.to_dict() for _, policy in sorted(transport_bridge_policy_catalog().items())]


def legacy_usage_payload(name: str, *, count: int = 1, release_id: str = '') -> dict[str, object]:
    """Build a normalized telemetry record for one legacy transport observation.

    Args:
        name: Bridge policy name.
        count: Number of observed legacy publishes.
        release_id: Optional release identifier attached by CI/release tooling.

    Returns:
        JSON-serializable telemetry record.

    Boundary behavior:
        The helper never enables legacy transport; it only records usage after a
        caller has already chosen to publish through a legacy channel.
    """
    policy = transport_bridge_policy(name)
    return {
        'time': datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'bridge': policy.name,
        'count': max(0, int(count)),
        'releaseId': str(release_id or os.environ.get('INSPECTION_RELEASE_ID', '') or ''),
        'deprecationPhase': policy.deprecation_phase,
        'sunsetRelease': policy.sunset_release,
        'removalCandidate': policy.removal_candidate,
        'zeroUsageRemovalAfterReleases': policy.zero_usage_removal_after_releases,
    }


def record_legacy_transport_usage(name: str, *, count: int = 1, telemetry_path: str | None = None) -> dict[str, object]:
    """Append legacy transport usage telemetry when a legacy channel is used.

    Args:
        name: Bridge policy name.
        count: Number of observed legacy publishes.
        telemetry_path: Optional JSONL output path. When omitted, the
            ``INSPECTION_TRANSPORT_LEGACY_TELEMETRY_PATH`` environment variable
            is used. Empty paths disable file writes but still return payload.

    Returns:
        The normalized telemetry payload.

    Raises:
        OSError: Propagated when an explicitly configured telemetry path cannot
        be written.

    Boundary behavior:
        Default runtime behavior is non-invasive: no file is written unless a
        release/CI/runtime profile supplies a telemetry path. This prevents unit
        tests and ad-hoc developer runs from polluting the workspace.
    """
    payload = legacy_usage_payload(name, count=count)
    policy = transport_bridge_policy(name)
    if not policy.telemetry_enabled:
        return payload
    raw_path = telemetry_path if telemetry_path is not None else os.environ.get('INSPECTION_TRANSPORT_LEGACY_TELEMETRY_PATH', '')
    target_text = str(raw_path or '').strip()
    if not target_text:
        return payload
    target = Path(target_text)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('a', encoding='utf-8') as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + '\n')
    return payload


def legacy_removal_status(name: str, release_usage_counts: Mapping[str, int] | None = None) -> dict[str, object]:
    """Evaluate whether a legacy bridge is a removal candidate.

    Args:
        name: Bridge policy name.
        release_usage_counts: Mapping from release id to observed legacy usage
            count, ordered or unordered. Only counts are used.

    Returns:
        Removal-gate status containing consecutive zero-usage release count and
        whether the configured threshold has been met.

    Boundary behavior:
        The status helper is pure and does not delete any bridge. Actual removal
        remains a release governance step backed by release notes and tagged
        rollback strategy.
    """
    policy = transport_bridge_policy(name)
    counts = list((release_usage_counts or {}).values())
    consecutive_zero = 0
    for count in reversed(counts):
        if int(count) == 0:
            consecutive_zero += 1
            continue
        break
    threshold_met = bool(policy.removal_candidate_when_zero_usage and consecutive_zero >= policy.zero_usage_removal_after_releases)
    return {
        'bridge': policy.name,
        'consecutiveZeroUsageReleases': consecutive_zero,
        'zeroUsageRemovalAfterReleases': policy.zero_usage_removal_after_releases,
        'removalCandidate': bool(policy.removal_candidate or threshold_met),
        'releaseNoteRequired': policy.release_note_required,
        'rollbackStrategy': policy.rollback_strategy,
    }

