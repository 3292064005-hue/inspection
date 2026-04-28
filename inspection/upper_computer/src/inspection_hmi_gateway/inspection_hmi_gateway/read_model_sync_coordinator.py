from __future__ import annotations

"""Read-model synchronization helpers.

This module separates sync-token calculation, readiness reporting, and
projection refresh planning from :mod:`read_model_repository` so the
repository can focus on serving query operations and delegating rebuild work.
"""

from dataclasses import dataclass
from typing import Any

from inspection_utils.model_common import ReadModelStore

from .read_model_policy import READ_MODEL_MODE_LEGACY, READ_MODEL_MODE_REPAIR, ReadModelPolicy


@dataclass(frozen=True, slots=True)
class ReadModelReadiness:
    """Materialized readiness snapshot for the SQLite read model."""

    mode: str
    source_sync_token: str
    materialized_sync_token: str
    stale: bool
    projection_available: bool
    repair_required: bool
    query_side_trace_refresh: str

    def as_dict(self) -> dict[str, Any]:
        """Return the readiness snapshot using the external response schema."""
        return {
            'mode': self.mode,
            'sourceSyncToken': self.source_sync_token,
            'materializedSyncToken': self.materialized_sync_token,
            'stale': self.stale,
            'projectionAvailable': self.projection_available,
            'repairRequired': self.repair_required,
            'querySideTraceRefresh': self.query_side_trace_refresh,
        }


@dataclass(frozen=True, slots=True)
class ProjectionRefreshPlan:
    """Refresh decision for the SQLite read model projection."""

    action: str
    source_sync_token: str
    materialized_sync_token: str
    reason: str = ''


def cached_sync_token(store: ReadModelStore) -> str:
    """Return the best available source sync token for the current runtime.

    Args:
        store: Runtime read-model store bound to the current log directory.

    Returns:
        Cached sync-state token when structured source files still match the
        cached state. Otherwise returns a freshly recomputed live token.

    Raises:
        No exception is intentionally raised.

    Boundary behavior:
        Missing or malformed sync-state payloads fall back to a live token
        recompute so stale projections are surfaced rather than masked.
    """
    state = store.load_sync_state()
    source_files = state.get('sourceFiles', {}) if isinstance(state.get('sourceFiles', {}), dict) else {}
    trace_token = str(state.get('traceToken', ''))
    required = ('result_csv', 'summary_jsonl', 'replay_manifest_jsonl', 'artifact_index_jsonl')
    if all(key in source_files for key in required) and trace_token:
        live_source_files = store.source_file_tokens()
        if all(str(source_files.get(key, '')) == str(live_source_files.get(key, '')) for key in required):
            return '|'.join([str(source_files[key]) for key in required] + [trace_token])
    return store.sync_token()


def build_readiness(store: ReadModelStore, policy: ReadModelPolicy, *, projection_available: bool) -> ReadModelReadiness:
    """Build a readiness snapshot for the current projection state."""
    source_sync_token = cached_sync_token(store)
    materialized_sync_token = store.materialized_sync_token()
    stale = source_sync_token != materialized_sync_token
    return ReadModelReadiness(
        mode=policy.normalized_mode().upper(),
        source_sync_token=source_sync_token,
        materialized_sync_token=materialized_sync_token,
        stale=stale,
        projection_available=projection_available,
        repair_required=stale or not projection_available,
        query_side_trace_refresh=policy.normalized_query_side_trace_refresh().upper(),
    )


def resolve_projection_refresh_plan(store: ReadModelStore, policy: ReadModelPolicy, *, projection_available: bool) -> ProjectionRefreshPlan:
    """Resolve whether the repository should no-op, rebuild, or require repair.

    Args:
        store: Runtime read-model store.
        policy: Effective read-model policy.
        projection_available: Whether SQLite currently contains projected data.

    Returns:
        A refresh plan describing the next action and current sync tokens.

    Raises:
        No exception is intentionally raised. The caller decides whether to
        convert a non-rebuild plan into an exception.

    Boundary behavior:
        Empty projections are treated as requiring action even when sync tokens
        happen to match, because an empty materialization cannot satisfy query
        requests.
    """
    source_sync_token = cached_sync_token(store)
    materialized_sync_token = store.materialized_sync_token()
    if source_sync_token == materialized_sync_token and projection_available:
        return ProjectionRefreshPlan(action='noop', source_sync_token=source_sync_token, materialized_sync_token=materialized_sync_token)

    mode = policy.normalized_mode()
    if mode == READ_MODEL_MODE_LEGACY:
        return ProjectionRefreshPlan(action='require_explicit_repair', source_sync_token=source_sync_token, materialized_sync_token=materialized_sync_token, reason='legacy_mode')
    if not projection_available and policy.bootstrap_repair_on_empty_db:
        return ProjectionRefreshPlan(action='rebuild', source_sync_token=source_sync_token, materialized_sync_token=materialized_sync_token, reason='bootstrap_repair_on_empty_db')
    if mode == READ_MODEL_MODE_REPAIR or policy.allow_runtime_repair_on_sync_mismatch:
        return ProjectionRefreshPlan(action='rebuild', source_sync_token=source_sync_token, materialized_sync_token=materialized_sync_token, reason='policy_allows_runtime_repair')
    return ProjectionRefreshPlan(action='require_explicit_repair', source_sync_token=source_sync_token, materialized_sync_token=materialized_sync_token, reason='stale_projection')
