from __future__ import annotations

from inspection_utils.model_common import DetectionSummary
from ..evidence_schema import aggregate_confidence
from ..postprocess.consistency_checker import apply_consistency_checks


def build_summary(context, recipe: dict, *, item_id: int, batch_id: str, trace_id: str) -> DetectionSummary:
    summary = DetectionSummary(item_id=item_id, batch_id=batch_id, trace_id=trace_id, recipe_id=recipe.get('recipe_id', 'default_recipe'))
    summary.color_name = str(context.outputs.get('color_name', 'unknown'))
    summary.color_ratio = float(context.outputs.get('color_ratio', 0.0))
    summary.qr_ok = bool(context.outputs.get('qr_ok', recipe.get('vision', {}).get('qr', {}).get('enabled', False) is False))
    summary.qr_text = str(context.outputs.get('qr_text', ''))
    summary.orientation_ok = bool(context.outputs.get('orientation_ok', True))
    summary.defect_type = str(context.outputs.get('defect_type', 'NONE'))
    if any(tag.startswith('quality:') for tag in context.warnings) and summary.defect_type == 'NONE':
        summary.defect_type = 'IMAGE_QUALITY'
    consistency_issues = apply_consistency_checks(context, recipe)
    context.warnings.extend(issue for issue in consistency_issues if issue not in context.warnings)
    summary.metrics = dict(context.metrics)
    summary.evidence = dict(context.evidence)
    summary.warnings = list(context.warnings)
    summary.valid = not any(w.startswith('blocking:') for w in summary.warnings)
    summary.score = aggregate_confidence(
        color_ratio=summary.color_ratio,
        qr_ok=summary.qr_ok,
        orientation_ok=summary.orientation_ok,
        quality_warning_count=len([w for w in summary.warnings if w.startswith('quality:') or w.startswith('warning:')]),
    )
    if not summary.valid and summary.defect_type == 'NONE':
        summary.defect_type = 'CONSISTENCY_ERROR'
    return summary
