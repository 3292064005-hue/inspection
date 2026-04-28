from __future__ import annotations

"""Shared model/projection helpers exposed behind a narrow boundary."""

from .models import CycleSummary, DecisionOutcome, DetectionSummary
from .read_model_projection import build_result_projection, safe_float, safe_int
from .read_model_store import ReadModelStore
from .result_identity import canonical_result_id

__all__ = [
    'CycleSummary',
    'DecisionOutcome',
    'DetectionSummary',
    'ReadModelStore',
    'build_result_projection',
    'canonical_result_id',
    'safe_float',
    'safe_int',
]
