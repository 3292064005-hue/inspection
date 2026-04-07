from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

START_COMMAND: Final[str] = 'start'
STOP_COMMAND: Final[str] = 'stop'
PAUSE_COMMAND: Final[str] = 'pause'
RESUME_COMMAND: Final[str] = 'resume'
RESET_COMMAND: Final[str] = 'reset'
CANCEL_COMMAND: Final[str] = 'cancel'
ENTER_MANUAL_COMMAND: Final[str] = 'enter_manual'
EXIT_MANUAL_COMMAND: Final[str] = 'exit_manual'
MANUAL_STEP_FEED_COMMAND: Final[str] = 'manual_step_feed'
MANUAL_STEP_CAPTURE_COMMAND: Final[str] = 'manual_step_capture'
MANUAL_STEP_SORT_COMMAND: Final[str] = 'manual_step_sort'

LEGACY_CONTROL_ALIASES: Final[dict[str, str]] = {
    'cancel_item': CANCEL_COMMAND,
}

CANONICAL_CONTROL_COMMANDS: Final[frozenset[str]] = frozenset(
    {
        START_COMMAND,
        STOP_COMMAND,
        PAUSE_COMMAND,
        RESUME_COMMAND,
        RESET_COMMAND,
        CANCEL_COMMAND,
        ENTER_MANUAL_COMMAND,
        EXIT_MANUAL_COMMAND,
        MANUAL_STEP_FEED_COMMAND,
        MANUAL_STEP_CAPTURE_COMMAND,
        MANUAL_STEP_SORT_COMMAND,
    }
)


def normalize_control_command(command: str | None) -> str:
    """Return the canonical control command string.

    Args:
        command: Raw action or command value received from UI, supervisor, or other transport.

    Returns:
        Canonical lowercase command string. Unknown values are returned as normalized lowercase strings
        so callers can decide whether to ignore or reject them.
    """
    normalized = str(command or '').strip().lower()
    if not normalized:
        return ''
    return LEGACY_CONTROL_ALIASES.get(normalized, normalized)


def extract_control_command(payload: Mapping[str, Any] | None) -> str:
    """Extract and normalize a control command from an envelope-like payload.

    Args:
        payload: Mapping that may contain ``action`` or ``command`` fields.

    Returns:
        Canonical normalized control command. Returns an empty string when the payload is missing or
        does not contain a usable command value.
    """
    if not isinstance(payload, Mapping):
        return ''
    raw = payload.get('action', payload.get('command', ''))
    if isinstance(raw, bytes):
        raw = raw.decode('utf-8', errors='ignore')
    return normalize_control_command(raw if isinstance(raw, str) else str(raw or ''))


def is_known_control_command(command: str | None) -> bool:
    """Return whether *command* maps to a known canonical control command.

    Args:
        command: Raw candidate command.

    Returns:
        ``True`` when the command is part of the canonical control-plane contract.
    """
    return normalize_control_command(command) in CANONICAL_CONTROL_COMMANDS
