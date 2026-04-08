from __future__ import annotations

"""Helpers for deterministic runtime parameter coercion.

The ROS launch system may forward parameters as native booleans, integers, or
strings depending on whether the node is running from a source workspace,
through a launch substitution, or from installed YAML/CLI overrides. Using
``bool(value)`` directly is unsafe because non-empty strings such as
``"false"`` evaluate to ``True`` in Python.
"""

from typing import Any

_TRUE_VALUES = {'1', 'true', 'yes', 'on'}
_FALSE_VALUES = {'0', 'false', 'no', 'off', ''}


def coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Coerce a launch/runtime parameter payload into a boolean.

    Args:
        value: Source value. Supported inputs include bool, int/float, str, and
            ``None``.
        default: Fallback value used when ``value`` is ``None`` or cannot be
            interpreted deterministically.

    Returns:
        Deterministic boolean value.

    Raises:
        No exception is raised. Unsupported values fall back to ``default``.

    Boundary behavior:
        Non-empty strings are *not* treated as truthy by presence alone. The
        string must match a recognized true/false token.
    """

    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES:
        return False
    return bool(default)


def parameter_as_bool(node: Any, name: str, *, default: bool = False) -> bool:
    """Read and coerce one ROS parameter into a deterministic boolean.

    Args:
        node: ROS node or node-like test double exposing ``get_parameter``.
        name: Parameter name.
        default: Fallback value when the parameter is absent or ambiguous.

    Returns:
        Coerced boolean value.

    Raises:
        No exception is raised. Unexpected parameter access errors fall back to
        ``default`` so lifecycle/autostart guards remain fail-safe.

    Boundary behavior:
        Parameters forwarded as strings from launch substitutions are parsed the
        same way as native booleans.
    """

    try:
        parameter = node.get_parameter(name)
    except Exception:
        return bool(default)
    return coerce_bool(getattr(parameter, 'value', None), default=default)
