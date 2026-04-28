from __future__ import annotations

"""Canonical command services for the gateway HTTP surface."""

from ..context import GatewayAppContext


class ActionCommandService:
    """Submit and cancel jobs through the canonical persisted action plane.

    Args:
        context: Bound gateway application context.

    Returns:
        None. Use :meth:`submit` and :meth:`cancel`.

    Raises:
        Exceptions from the action job service propagate to the caller.

    Boundary behavior:
        This service is the only HTTP command entrypoint for action execution.
        Legacy compatibility wrappers have been removed, so all mutating control
        requests must flow through persisted action jobs.
    """

    def __init__(self, context: GatewayAppContext) -> None:
        self.context = context

    def submit(self, kind: str, payload: dict[str, object], *, actor: dict[str, object]) -> dict[str, object]:
        """Submit one canonical action job."""
        return self.context.action_job_service().submit(kind, payload=payload, actor=actor)

    def cancel(self, job_id: str, *, actor: dict[str, object]) -> dict[str, object]:
        """Cancel one previously submitted action job."""
        return self.context.action_job_service().cancel(job_id, actor=actor)
