from __future__ import annotations

"""Submission policy for maintenance-mode diagnostic actions.

This module centralizes the server-side guardrails for hazardous diagnostics
actions so HTTP callers, multiple browser sessions, and direct action-plane
submissions all share one source of truth.
"""

from dataclasses import dataclass
import os
from pathlib import Path

from inspection_utils.config_common import load_yaml
from inspection_utils.io_common import resolve_resource_path

DEFAULT_POLICY_PATH = 'config/system/diagnostic_actions.yaml'
DEFAULT_DIAGNOSTIC_KINDS = (
    'diagnostic_capture_frame',
    'diagnostic_test_lighting',
    'diagnostic_test_sort_actuator',
)


class DiagnosticActionPolicyError(RuntimeError):
    """Raised when the diagnostics action policy configuration is invalid."""


@dataclass(frozen=True, slots=True)
class DiagnosticActionPolicy:
    """Runtime submission rules for hazardous diagnostic actions.

    Args:
        cooldown_ms: Minimum time between two successful submissions of the
            same diagnostics action kind.
        require_maintenance_enabled: Whether the server must observe
            ``maintenance.enabled`` before allowing submission.
        serialized_kinds: Action kinds that share a global in-flight mutex.

    Boundary behavior:
        Unknown action kinds never opt into the diagnostics policy implicitly.
        The policy is intentionally conservative and fail-closed.
    """

    cooldown_ms: int = 6500
    require_maintenance_enabled: bool = True
    serialized_kinds: tuple[str, ...] = DEFAULT_DIAGNOSTIC_KINDS

    def applies_to(self, kind: str) -> bool:
        return str(kind or '').strip().lower() in set(self.serialized_kinds)


def _as_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _normalize_kinds(raw: object) -> tuple[str, ...]:
    if raw is None:
        return DEFAULT_DIAGNOSTIC_KINDS
    if not isinstance(raw, list):
        raise DiagnosticActionPolicyError('diagnostic_actions.serialized_kinds must be a list')
    normalized = tuple(str(item).strip().lower() for item in raw if str(item).strip())
    return normalized or DEFAULT_DIAGNOSTIC_KINDS


def _normalize_cooldown_ms(raw: object) -> int:
    if raw in (None, ''):
        return 6500
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise DiagnosticActionPolicyError('diagnostic_actions.cooldown_ms must be an integer') from exc
    if value < 0:
        raise DiagnosticActionPolicyError('diagnostic_actions.cooldown_ms must be >= 0')
    return value


def load_diagnostic_action_policy(config_path: str | Path = DEFAULT_POLICY_PATH) -> DiagnosticActionPolicy:
    """Load diagnostics action policy from config/system with env overrides."""
    resolved = resolve_resource_path(str(config_path), package_name='inspection_hmi_gateway', start=__file__)
    payload = load_yaml(resolved) if resolved.exists() else {}
    section = payload.get('diagnostic_actions', {}) if isinstance(payload, dict) else {}
    if section and not isinstance(section, dict):
        raise DiagnosticActionPolicyError('diagnostic_actions section must be a mapping')
    cooldown_ms = _normalize_cooldown_ms(os.environ.get('INSPECTION_DIAGNOSTIC_ACTION_COOLDOWN_MS', section.get('cooldown_ms')))
    require_maintenance_enabled = _as_bool(
        os.environ.get('INSPECTION_DIAGNOSTIC_ACTION_REQUIRE_MAINTENANCE_ENABLED', section.get('require_maintenance_enabled')),
        default=True,
    )
    serialized_kinds = _normalize_kinds(section.get('serialized_kinds'))
    return DiagnosticActionPolicy(
        cooldown_ms=cooldown_ms,
        require_maintenance_enabled=require_maintenance_enabled,
        serialized_kinds=serialized_kinds,
    )
