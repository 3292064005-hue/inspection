from __future__ import annotations

"""Minimal runtime-state helpers for nodes intentionally outside lifecycle governance."""

from typing import Any


class ExternalServiceRuntimeMixin:
    """Expose lightweight runtime state without lifecycle control surfaces.

    This mixin is used by nodes that must remain outside ROS 2 lifecycle
    governance according to the runtime-topology manifest. It provides the
    minimal ``lifecycle_state`` / ``is_active`` surface consumed by existing
    diagnostics and shutdown guards while deliberately omitting lifecycle
    subscriptions, compatibility bridges, or transition handlers.
    """

    lifecycle_node_name: str
    _external_lifecycle_state: str

    def setup_external_runtime(self, *, node_name: str, initial_state: str = 'ACTIVE') -> None:
        """Initialize one external-service runtime state surface.

        Args:
            node_name: Canonical runtime-topology node name represented by this
                process. This can differ from the underlying ROS node name when
                the process intentionally models one higher-level external
                service boundary.
            initial_state: Starting runtime state label. Defaults to ``ACTIVE``.

        Returns:
            None.

        Raises:
            ValueError: If ``node_name`` or ``initial_state`` is blank.

        Boundary behavior:
            The helper only records local state. It does not create lifecycle
            subscriptions, native lifecycle services, or compatibility bridges.
        """
        normalized_name = str(node_name or '').strip()
        normalized_state = str(initial_state or '').strip().upper()
        if not normalized_name:
            raise ValueError('external runtime node_name is required')
        if not normalized_state:
            raise ValueError('external runtime initial_state is required')
        self.lifecycle_node_name = normalized_name
        self._external_lifecycle_state = normalized_state

    @property
    def lifecycle_state(self) -> str:
        """Return the current external-service runtime state label."""
        return str(getattr(self, '_external_lifecycle_state', 'ACTIVE') or 'ACTIVE').upper()

    def is_active(self) -> bool:
        """Return ``True`` when the external-service runtime should be treated as active."""
        return self.lifecycle_state in {'ACTIVE', 'RUNNING', 'READY', 'OK'}

    def mark_external_runtime_state(self, state: str) -> None:
        """Update the external runtime-state label.

        Args:
            state: New state label.

        Returns:
            None.

        Raises:
            ValueError: If ``state`` is blank.
        """
        normalized_state = str(state or '').strip().upper()
        if not normalized_state:
            raise ValueError('external runtime state is required')
        self._external_lifecycle_state = normalized_state

    def transition_lifecycle(self, transition: str, *, reason: str = '') -> dict[str, Any]:
        """Reject lifecycle transition attempts for external-service nodes.

        Args:
            transition: Requested lifecycle transition label.
            reason: Optional transition reason.

        Returns:
            Structured rejection payload for diagnostics.

        Boundary behavior:
            External-service nodes never mutate state through lifecycle control
            commands; callers must use process-specific health or shutdown
            semantics instead.
        """
        return {
            'node': self.lifecycle_node_name,
            'transition': str(transition or '').upper(),
            'reason': str(reason or ''),
            'success': False,
            'message': 'external_service_runtime_does_not_accept_lifecycle_transitions',
            'lifecycle_state': self.lifecycle_state,
        }
