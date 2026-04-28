from __future__ import annotations

"""Shared runtime primitives exposed behind a stable boundary.

This boundary must remain import-safe in non-ROS test environments. Heavy ROS
node mixins are therefore imported lazily behind soft fallbacks so modules that
only need QoS helpers can still be imported without ``std_msgs`` installed.
"""

from .qos import qos_compatibility_warnings, qos_policy_matrix, qos_profile, qos_summary
from .typed_interfaces import assert_typed_interfaces_available


class _MissingManagedNodeMixin:
    def __init__(self, *_args, **_kwargs) -> None:  # pragma: no cover - guardrail
        raise ModuleNotFoundError('ROS managed-node dependencies are not available in this environment.')


class _MissingInspectionRuntimeNode:
    def __init__(self, *_args, **_kwargs) -> None:  # pragma: no cover - guardrail
        raise ModuleNotFoundError('ROS runtime-node dependencies are not available in this environment.')


class _MissingStandardRuntimeNode:
    def __init__(self, *_args, **_kwargs) -> None:  # pragma: no cover - guardrail
        raise ModuleNotFoundError('ROS runtime-node dependencies are not available in this environment.')


class _MissingExternalServiceRuntimeMixin:
    def __init__(self, *_args, **_kwargs) -> None:  # pragma: no cover - guardrail
        raise ModuleNotFoundError('ROS runtime-node dependencies are not available in this environment.')


try:  # pragma: no cover - exercised indirectly in ROS-enabled environments
    from .managed_node import ManagedNodeMixin  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - import-safe fallback for pure unit tests
    ManagedNodeMixin = _MissingManagedNodeMixin  # type: ignore[assignment]

try:  # pragma: no cover - exercised indirectly in ROS-enabled environments
    from .runtime_node import InspectionRuntimeNode, StandardRuntimeNode  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - import-safe fallback for pure unit tests
    InspectionRuntimeNode = _MissingInspectionRuntimeNode  # type: ignore[assignment]
    StandardRuntimeNode = _MissingStandardRuntimeNode  # type: ignore[assignment]

try:  # pragma: no cover - exercised indirectly in ROS-enabled environments
    from .external_runtime import ExternalServiceRuntimeMixin  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - import-safe fallback for pure unit tests
    ExternalServiceRuntimeMixin = _MissingExternalServiceRuntimeMixin  # type: ignore[assignment]


__all__ = [
    'InspectionRuntimeNode',
    'StandardRuntimeNode',
    'ManagedNodeMixin',
    'ExternalServiceRuntimeMixin',
    'assert_typed_interfaces_available',
    'qos_compatibility_warnings',
    'qos_policy_matrix',
    'qos_profile',
    'qos_summary',
]
