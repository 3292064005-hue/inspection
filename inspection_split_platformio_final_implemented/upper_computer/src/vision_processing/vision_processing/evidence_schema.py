from __future__ import annotations

from typing import Any


def detector_evidence(detector_name: str, *, status: str = 'OK', score: float = 0.0, warnings: list[str] | None = None, overlay_refs: list[str] | None = None, **raw_metrics: Any) -> dict[str, Any]:
    return {
        'detector_name': detector_name,
        'status': status,
        'score': float(score),
        'warnings': list(warnings or []),
        'overlay_refs': list(overlay_refs or []),
        'raw_metrics': raw_metrics,
    }


def aggregate_confidence(*, color_ratio: float, qr_ok: bool, orientation_ok: bool, quality_warning_count: int) -> float:
    base = 0.0
    base += min(0.6, max(0.0, float(color_ratio)))
    base += 0.2 if qr_ok else 0.0
    base += 0.2 if orientation_ok else 0.0
    penalty = min(0.4, 0.12 * max(0, quality_warning_count))
    return round(max(0.0, min(1.0, base - penalty)), 4)
