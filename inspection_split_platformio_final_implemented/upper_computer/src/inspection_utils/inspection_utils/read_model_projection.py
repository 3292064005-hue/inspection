from __future__ import annotations

from typing import Any

from .logging_tools import safe_json_loads
from .result_identity import canonical_result_id


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def build_result_projection(*, row: dict[str, Any], summary: dict[str, Any], trace_bundle: dict[str, Any]) -> dict[str, Any]:
    """Build a gateway/HMI-facing result projection.

    Args:
        row: Raw CSV-style result row.
        summary: Per-trace cycle summary payload.
        trace_bundle: Enriched trace/evidence bundle.

    Returns:
        A normalized result detail/list payload consumed by gateway APIs.
    """
    trace_id = str(row.get('trace_id', ''))
    result_id = canonical_result_id(result_id=row.get('result_id', ''), trace_id=trace_id, batch_id=row.get('batch_id', ''), item_id=row.get('item_id', ''), timestamp=row.get('time', ''))
    detail = safe_json_loads(row.get('detail_json', '') or '{}')
    timings = summary.get('phase_timings_ms', {}) if isinstance(summary.get('phase_timings_ms', {}), dict) else {}
    decision = str(summary.get('decision', '') or ('NG' if str(summary.get('final_status', '')).upper() == 'FAULT' else 'RECHECK'))
    if decision not in {'OK', 'NG', 'RECHECK'}:
        decision = 'RECHECK'
    score = row.get('score', '')
    try:
        metric_value = float(score)
    except Exception:
        metric_value = None
    warnings = detail.get('warnings', []) if isinstance(detail.get('warnings', []), list) else []
    explanation = [str(item) for item in warnings if item]
    if not explanation:
        defect_type = str(row.get('defect_type', ''))
        category = str(row.get('category', ''))
        explanation = [item for item in [defect_type if defect_type and defect_type != 'NONE' else '', category] if item]
    phase_total = safe_float(summary.get('cycle_time_sec', 0.0)) * 1000.0
    feeding = safe_float(timings.get('feed_wait_ack', timings.get('feeding', 0.0)))
    capture = safe_float(timings.get('capture_wait_frame', timings.get('capture', 0.0)))
    analyze = safe_float(timings.get('analyze_wait', timings.get('analyze', detail.get('processing_ms', 0.0))))
    sorting = (
        safe_float(timings.get('sort_wait_ack', 0.0))
        + safe_float(timings.get('sort_wait_done', 0.0))
        + safe_float(timings.get('sorting', 0.0))
    )
    return {
        'id': result_id,
        'resultId': result_id,
        'timestamp': str(row.get('time', '')),
        'traceId': trace_id,
        'batchId': str(row.get('batch_id', '')),
        'itemId': safe_int(row.get('item_id', -1), default=-1),
        'recipeId': str(row.get('recipe_id', '')),
        'decision': decision,
        'category': str(row.get('category', '')),
        'defectType': str(row.get('defect_type', '')),
        'qrText': str(row.get('qr_text', '')),
        'metricValue': metric_value,
        'metricLabel': 'score' if metric_value is not None else '',
        'cycleMs': round(phase_total if phase_total > 0 else analyze, 3),
        'imagePath': str(row.get('image_path', '')),
        'overlayPath': str(row.get('annotated_image_path', '')),
        'traceUrl': str(trace_bundle.get('traceUrl', '')),
        'artifactCount': safe_int(trace_bundle.get('artifactCount', 0), default=0),
        'runArtifacts': trace_bundle.get('runArtifacts', {}),
        'configSnapshot': trace_bundle.get('configSnapshot', {}),
        'artifacts': trace_bundle.get('artifacts', []),
        'traceSummary': trace_bundle.get('summary', {}),
        'explanation': explanation or ['规则检测完成'],
        'breakdown': {
            'feedingMs': round(feeding, 3),
            'captureMs': round(capture, 3),
            'analyzeMs': round(analyze, 3),
            'sortingMs': round(sorting, 3),
            'totalMs': round(phase_total if phase_total > 0 else (feeding + capture + analyze + sorting), 3),
        },
    }
