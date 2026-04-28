from __future__ import annotations

"""HTTP request schemas for the canonical action plane.

These models are the typed request boundary for FastAPI/OpenAPI generation.
They intentionally keep transport semantics close to the action runtime payloads
so request validation, generated frontend contracts, and action-job submission
cannot drift independently.
"""

from typing import Any

from pydantic import BaseModel, Field

try:  # pydantic v2
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - pydantic v1 fallback
    ConfigDict = None  # type: ignore[assignment]


class StrictRequestModel(BaseModel):
    """Base request model with forbidden unknown fields.

    Boundary behavior:
        Unknown JSON fields are rejected at the HTTP boundary so the canonical
        action plane stays authoritative and callers cannot silently depend on
        undeclared payload keys.
    """

    if ConfigDict is not None:  # pydantic v2
        model_config = ConfigDict(extra='forbid', populate_by_name=True)
    else:  # pragma: no cover - pydantic v1 fallback
        class Config:
            extra = 'forbid'
            allow_population_by_field_name = True

    def to_payload(self) -> dict[str, Any]:
        """Serialize the request model into an action-job payload dictionary."""
        dump = getattr(self, 'model_dump', None)
        if callable(dump):
            return dump(exclude_none=True, by_alias=True)
        return self.dict(exclude_none=True, by_alias=True)  # pragma: no cover


class EmptyActionRequest(StrictRequestModel):
    """Empty payload used by actions that carry no caller-provided parameters."""


class StartBatchRequest(StrictRequestModel):
    """Start one production batch.

    Args:
        recipeId: Activated recipe identifier to execute.
        batchId: Optional caller-provided batch identifier.
    """

    recipeId: str = Field(..., min_length=1, description='Activated recipe identifier used by the next batch run.')
    batchId: str | None = Field(default=None, min_length=1, description='Optional caller-provided batch identifier.')


class ResetStationRequest(StrictRequestModel):
    """Reset one station fault and optionally resume automation."""

    reason: str | None = Field(default=None, description='Optional operator reason stored with the reset request.')
    resumeAfter: bool = Field(default=False, description='Whether the station should resume automation after the fault reset completes.')


class ExecuteReplayRequest(StrictRequestModel):
    """Replay one persisted inspection trace."""

    traceId: str = Field(..., min_length=1, description='Persisted trace identifier to replay.')


class ExportBatchRequest(StrictRequestModel):
    """Export one persisted batch bundle."""

    batchId: str = Field(..., min_length=1, description='Batch identifier to export.')


class RunBenchmarkRequest(StrictRequestModel):
    """Run the explicitly synthetic benchmark workflow."""

    sampleCount: int | None = Field(default=None, ge=1, description='Optional number of synthetic samples to generate.')
    profileName: str | None = Field(default=None, min_length=1, description='Optional benchmark profile name.')


class SwitchRecipeRequest(StrictRequestModel):
    """Validate one recipe and optionally activate it for the next run."""

    recipeId: str = Field(..., min_length=1, description='Recipe identifier to validate and optionally activate.')
    dryRun: bool = Field(default=False, description='When true, validate the recipe without activating it.')


class MaintenanceModeRequest(StrictRequestModel):
    """Switch maintenance mode through the canonical action plane."""

    enabled: bool = Field(..., description='Target maintenance-mode state.')
