from __future__ import annotations

"""Thread-safe gateway read-model state primitives.

The gateway runtime updates station state from the ROS executor thread while the
FastAPI and WebSocket surfaces concurrently read that state on the HTTP event
loop. This module provides a single-writer transaction boundary with immutable
snapshots for readers so the gateway no longer leaks half-applied updates across
threads.
"""

from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Callable, TypeVar

from .runtime_components import utc_now

T = TypeVar('T')


@dataclass
class GatewayState:
    """Canonical mutable gateway read model.

    The object is intentionally plain and serialization-friendly so it can be
    deep-copied into response snapshots and persisted into tests with minimal
    ceremony.
    """

    phase: str = 'BOOT'
    mode: str = 'IDLE'
    supervisor_mode: str = 'STOPPED'
    batch_id: str = 'BATCH_DEMO'
    active_recipe_id: str = ''
    active_recipe_name: str = '--'
    active_recipe_version: str = ''
    active_recipe_generation: str = ''
    recipe_activation_state: str = ''
    cycle_index: int = 0
    last_updated_at: str = field(default_factory=utc_now)
    guidance: str = '等待系统连接。'
    maintenance_requested: bool = False
    maintenance_active: bool = False
    maintenance_transition_state: str = 'LOCKED'
    absolute_stats: dict[str, float] = field(
        default_factory=lambda: {
            'total': 0,
            'ok': 0,
            'ng': 0,
            'recheck': 0,
            'yieldRate': 0.0,
            'avgCycleMs': 0.0,
        }
    )
    batch_baseline: dict[str, float] = field(default_factory=lambda: {'total': 0, 'ok': 0, 'ng': 0, 'recheck': 0})
    continuous_run_count: int = 0
    latest_frame: dict[str, Any] = field(default_factory=lambda: {'url': '', 'capturedAt': utc_now(), 'annotated': True})
    latest_fault: dict[str, Any] | None = None
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    latest_orchestrator_advice: dict[str, Any] | None = None
    pending_batch_id: str = 'BATCH_DEMO'
    heartbeats: dict[str, dict[str, Any]] = field(default_factory=dict)

    def maintenance_payload(self) -> dict[str, Any]:
        """Return the canonical maintenance-state projection.

        Returns:
            A serialization-friendly maintenance snapshot used by HTTP and WS
            consumers.
        """
        return {
            'requested': bool(self.maintenance_requested),
            'enabled': bool(self.maintenance_active),
            'transitionState': str(self.maintenance_transition_state),
            'supervisorMode': str(self.supervisor_mode),
            'source': 'system_snapshot',
        }

    def snapshot_payload(self) -> dict[str, Any]:
        """Return the public station state payload served by HTTP and WS."""
        return {
            'phase': self.phase,
            'mode': self.mode,
            'supervisorMode': self.supervisor_mode,
            'batchId': self.batch_id,
            'activeRecipeId': self.active_recipe_id,
            'activeRecipeName': self.active_recipe_name,
            'activeRecipeVersion': self.active_recipe_version,
            'activeRecipeGeneration': self.active_recipe_generation,
            'recipeActivationState': self.recipe_activation_state,
            'cycleIndex': self.cycle_index,
            'lastUpdatedAt': self.last_updated_at,
            'guidance': self.guidance,
            'maintenance': self.maintenance_payload(),
        }

    def stats_payload(self) -> dict[str, Any]:
        """Return batch-relative count statistics."""
        total = max(0.0, self.absolute_stats['total'] - self.batch_baseline['total'])
        ok = max(0.0, self.absolute_stats['ok'] - self.batch_baseline['ok'])
        ng = max(0.0, self.absolute_stats['ng'] - self.batch_baseline['ng'])
        recheck = max(0.0, self.absolute_stats['recheck'] - self.batch_baseline['recheck'])
        yield_rate = ok / total if total > 0 else 0.0
        return {
            'total': int(total),
            'ok': int(ok),
            'ng': int(ng),
            'recheck': int(recheck),
            'yieldRate': round(yield_rate, 4),
            'continuousRunCount': int(self.continuous_run_count),
            'avgCycleMs': round(float(self.absolute_stats['avgCycleMs']), 3),
        }


class GatewayStateView:
    """Compatibility proxy exposing state reads/writes through the store.

    Older tests and adapters still expect attribute-level access like
    ``app.state.active_recipe_id``. The proxy preserves that API while routing
    every access through :class:`GatewayStateStore`.
    """

    def __init__(self, store: 'GatewayStateStore') -> None:
        object.__setattr__(self, '_store', store)

    def __getattr__(self, name: str) -> Any:
        return self._store.read(lambda state: deepcopy(getattr(state, name)))

    def __setattr__(self, name: str, value: Any) -> None:
        self._store.mutate(lambda state: setattr(state, name, value))

    def snapshot_payload(self) -> dict[str, Any]:
        return self._store.snapshot_payload()

    def stats_payload(self) -> dict[str, Any]:
        return self._store.stats_payload()

    @property
    def version(self) -> int:
        return self._store.version


class GatewayStateStore:
    """Thread-safe transaction boundary for gateway read-model state."""

    def __init__(self, initial: GatewayState | None = None) -> None:
        self._lock = RLock()
        self._state = deepcopy(initial) if initial is not None else GatewayState()
        self._version = 0
        self.view = GatewayStateView(self)

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def read(self, reader: Callable[[GatewayState], T]) -> T:
        """Execute a read callback against the current state under lock."""
        with self._lock:
            return reader(self._state)

    def mutate(self, mutator: Callable[[GatewayState], Any]) -> GatewayState:
        """Apply one atomic mutation and return a deep-copied post-state.

        Args:
            mutator: Callback that mutates the canonical state in place.

        Returns:
            A deep-copied snapshot of the state after the mutation commits.

        Raises:
            Any exception raised by ``mutator``.

        Boundary behavior:
            The internal version counter increments only after the full mutation
            callback completes successfully.
        """
        with self._lock:
            mutator(self._state)
            self._version += 1
            return deepcopy(self._state)

    def snapshot(self) -> GatewayState:
        """Return a deep-copied state snapshot."""
        with self._lock:
            return deepcopy(self._state)

    def snapshot_payload(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state.snapshot_payload())

    def stats_payload(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state.stats_payload())

    def diagnostics(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._state.diagnostics)

    def heartbeats(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return deepcopy(self._state.heartbeats)
