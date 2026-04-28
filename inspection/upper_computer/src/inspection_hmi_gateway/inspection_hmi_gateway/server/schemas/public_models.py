from __future__ import annotations

"""Typed request schemas for public non-action HTTP APIs.

These models back the generated frontend SDK for public gateway endpoints outside
of the canonical action plane. They ensure OpenAPI request bodies remain
strongly typed so frontend contract generation does not fall back to generic
``Record<string, unknown>`` payloads.
"""

from pydantic import Field

from .action_models import StrictRequestModel


class LoginGatewaySessionRequest(StrictRequestModel):
    """Authenticate one gateway session.

    Args:
        username: Operator login name.
        password: Operator password.

    Returns:
        The request payload serialized through :meth:`to_payload`.

    Raises:
        ValidationError: Raised by Pydantic when required fields are missing or
            empty.

    Boundary behavior:
        Unknown JSON keys are rejected so the login contract cannot silently
        drift from the frontend SDK.
    """

    username: str = Field(..., min_length=1, description='Operator login name.')
    password: str = Field(..., min_length=1, description='Operator password.')


class ChangeGatewayPasswordRequest(StrictRequestModel):
    """Change the password of the current authenticated session."""

    currentPassword: str = Field(..., min_length=1, description='Current password bound to the active session.')
    newPassword: str = Field(..., min_length=1, description='Replacement password for the active session.')


class RecipeSortRuleRequest(StrictRequestModel):
    """One rule shown in the HMI recipe editor."""

    condition: str = Field(..., min_length=1, description='Predicate expression used to match one inspection outcome.')
    action: str = Field(..., min_length=1, description='Sort action triggered when the condition evaluates to true.')


class SaveRecipeRequest(StrictRequestModel):
    """Persist one HMI recipe profile.

    The request mirrors the editable recipe profile used by the frontend. It is
    intentionally typed so the generated SDK can provide an exact payload shape
    instead of falling back to ``Record<string, unknown>``.
    """

    id: str = Field(..., min_length=1, description='Stable recipe identifier.')
    name: str = Field(..., min_length=1, description='Recipe display name shown in the HMI.')
    version: str = Field(..., min_length=1, description='Semantic recipe version string.')
    targetPart: str = Field(..., min_length=1, description='Target part or product family described by the recipe.')
    roi: list[int] = Field(..., min_length=4, max_length=4, description='Color ROI [x, y, w, h].')
    qrRoi: list[int] = Field(..., min_length=4, max_length=4, description='QR ROI [x, y, w, h].')
    thresholdsSummary: str = Field(..., min_length=1, description='Human-readable summary of the effective thresholds.')
    sortRules: list[RecipeSortRuleRequest] = Field(default_factory=list, description='Ordered HMI sort rules projected into the recipe metadata.')
    enabled: bool = Field(default=False, description='Whether the recipe is currently active in the HMI projection.')
    updatedAt: str | None = Field(default=None, description='Optional updated-at timestamp supplied by the HMI editor.')
    updatedBy: str | None = Field(default=None, description='Optional operator name attributed to the edit.')
    changeNote: str | None = Field(default=None, description='Optional free-form change note persisted into the recipe metadata.')
