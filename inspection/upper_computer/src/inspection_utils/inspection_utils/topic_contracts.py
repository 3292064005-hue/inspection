from __future__ import annotations

"""Canonical ROS topic definitions shared across the inspection workspace.

The module centralizes high-risk topic names whose semantics are coupled to the
main control loop. It separates business decision output from device execution
requests while preserving one explicit compatibility topic for legacy observers
through the migration window.
"""

DECISION_OUTPUT_TOPIC = '/inspection/decision_output'
SORT_REQUEST_TOPIC = '/station/sort_request'
SORT_REQUEST_LEGACY_TOPIC = '/station/sort_cmd'

__all__ = [
    'DECISION_OUTPUT_TOPIC',
    'SORT_REQUEST_TOPIC',
    'SORT_REQUEST_LEGACY_TOPIC',
]
