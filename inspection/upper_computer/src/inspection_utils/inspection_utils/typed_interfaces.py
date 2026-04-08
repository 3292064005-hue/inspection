from __future__ import annotations

"""Utilities for enforcing generated ROS typed-interface availability.

The workspace now treats typed transport messages as first-class runtime
contracts. Pure Python unit-test environments may still lack generated ROS
interface modules, but release-mode launch/build flows must fail fast instead of
silently degrading to legacy ``std_msgs/String`` traffic.
"""

import os
from typing import Any, Mapping

_TYPED_INTERFACE_REQUIRE_ENV = 'INSPECTION_REQUIRE_TYPED_INTERFACES'
_TYPED_INTERFACE_MODE_ENV = 'INSPECTION_TYPED_INTERFACE_MODE'


def _env_flag(name: str, *, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {'1', 'true', 'yes', 'on'}


def typed_interfaces_required() -> bool:
    """Return whether startup must fail when generated typed ROS interfaces are missing.

    Returns:
        ``True`` when the current process runs in a strict typed-interface mode.

    Boundary behavior:
        The explicit boolean environment variable takes precedence. Otherwise the
        mode variable accepts ``required/strict`` to force startup failure and
        ``optional/legacy`` to permit compatibility fallback.
    """

    if _TYPED_INTERFACE_REQUIRE_ENV in os.environ:
        return _env_flag(_TYPED_INTERFACE_REQUIRE_ENV, default=False)
    mode = str(os.environ.get(_TYPED_INTERFACE_MODE_ENV, 'optional')).strip().lower() or 'optional'
    return mode in {'required', 'strict', 'enforced'}


def missing_interface_symbols(symbols: Mapping[str, Any]) -> list[str]:
    """Return the interface symbol names that are currently unavailable."""
    return sorted(name for name, value in symbols.items() if value is None)


def assert_typed_interfaces_available(*, consumer: str, symbols: Mapping[str, Any]) -> None:
    """Fail fast when a strict runtime requires generated typed interfaces.

    Args:
        consumer: Human-readable node/component name used in the error message.
        symbols: Mapping from interface symbol names to imported message classes.

    Raises:
        RuntimeError: When strict typed-interface mode is enabled and one or more
            symbols are unavailable.

    Boundary behavior:
        In optional mode the helper is a no-op so pure Python unit tests can keep
        importing modules without generated ROS artifacts.
    """

    missing = missing_interface_symbols(symbols)
    if not missing or not typed_interfaces_required():
        return
    joined = ', '.join(missing)
    raise RuntimeError(
        f'{consumer} requires generated ROS typed interfaces, but the following '
        f'symbols are unavailable: {joined}. Build/source inspection_interfaces '
        f'and dependent packages before starting this runtime.'
    )
