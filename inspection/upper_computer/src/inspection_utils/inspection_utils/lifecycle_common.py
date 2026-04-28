from __future__ import annotations

"""Lifecycle-governance boundary helpers for supervisor/diagnostics packages."""

from .lifecycle_matrix import (
    allows_lifecycle_fallback,
    is_standard_node,
    lifecycle_governance_matrix,
    normalize_governed_node_name,
    requires_native_lifecycle,
)

__all__ = [
    'allows_lifecycle_fallback',
    'is_standard_node',
    'lifecycle_governance_matrix',
    'normalize_governed_node_name',
    'requires_native_lifecycle',
]
