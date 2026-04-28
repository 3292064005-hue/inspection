from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from hashlib import sha1
from typing import Any
import json

import cv2
import numpy as np

from inspection_utils.vision_common import crop_roi
from inspection_utils.vision_common import PluginManifest
from inspection_utils.model_common import DetectionSummary
from .evidence_schema import detector_evidence
from .pipeline.detector_registry import DetectorRegistry
from .pipeline.pipeline_manager import PipelineManager
from .pipeline.stage_base import PipelineStage


@dataclass(slots=True)
class PipelineContext:
    image: np.ndarray
    debug_views: dict[str, np.ndarray] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=lambda: {'detectors': {}})
    warnings: list[str] = field(default_factory=list)
    outputs: dict[str, Any] = field(default_factory=dict)

    def add_detector_evidence(self, name: str, payload: dict[str, object]) -> None:
        detectors = self.evidence.setdefault('detectors', {})
        if isinstance(detectors, dict):
            detectors[name] = payload


class QualityStage(PipelineStage):
    name = 'quality'

    def run(self, context: PipelineContext, recipe: dict) -> None:
        gray = cv2.cvtColor(context.image, cv2.COLOR_BGR2GRAY)
        brightness = float(np.mean(gray))
        blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        context.metrics['mean_brightness'] = round(brightness, 3)
        context.metrics['blur_variance'] = round(blur_var, 3)
        quality_cfg = recipe.get('vision', {}).get('quality', {}) or {}
        min_brightness = float(quality_cfg.get('min_brightness', 25.0))
        max_brightness = float(quality_cfg.get('max_brightness', 245.0))
        min_blur_variance = float(quality_cfg.get('min_blur_variance', 15.0))
        if brightness < min_brightness:
            context.warnings.append('quality:too_dark')
        if brightness > max_brightness:
            context.warnings.append('quality:over_exposed')
        if blur_var < min_blur_variance:
            context.warnings.append('quality:too_blurry')
        quality_warnings = [w for w in context.warnings if w.startswith('quality:')]
        quality_score = 1.0 - min(1.0, len(quality_warnings) * 0.34)
        context.add_detector_evidence('quality', detector_evidence('quality', status='WARN' if quality_warnings else 'OK', score=quality_score, warnings=quality_warnings, brightness=round(brightness, 3), blur_variance=round(blur_var, 3), min_brightness=min_brightness, max_brightness=max_brightness, min_blur_variance=min_blur_variance))


class DetectorBase:
    name = 'detector'
    config_key = ''

    def enabled(self, recipe: dict) -> bool:
        if not self.config_key:
            return True
        cfg = recipe.get('vision', {}).get(self.config_key, {})
        return bool(cfg.get('enabled', True))

    def config(self, recipe: dict) -> dict:
        return recipe.get('vision', {}).get(self.config_key, {}) or {}

    def run(self, context: PipelineContext, recipe: dict) -> None:
        raise NotImplementedError


class ColorDetector(DetectorBase):
    name = 'color'
    config_key = 'color'

    def run(self, context: PipelineContext, recipe: dict) -> None:
        config = self.config(recipe)
        roi = crop_roi(context.image, config.get('roi'))
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        best_name = 'unknown'
        best_ratio = 0.0
        best_mask = np.zeros(roi.shape[:2], dtype=np.uint8)
        total = max(1, roi.shape[0] * roi.shape[1])
        for name, ranges in (config.get('hsv_ranges') or {}).items():
            mask_total = np.zeros(roi.shape[:2], dtype=np.uint8)
            for r in ranges:
                lower = np.array(r[:3], dtype=np.uint8)
                upper = np.array(r[3:], dtype=np.uint8)
                mask_total = cv2.bitwise_or(mask_total, cv2.inRange(hsv, lower, upper))
            ratio = float(cv2.countNonZero(mask_total)) / float(total)
            if ratio > best_ratio:
                best_ratio = ratio
                best_name = name
                best_mask = mask_total
        vis = roi.copy()
        contours, _ = cv2.findContours(best_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cv2.drawContours(vis, contours, -1, (255, 255, 255), 2)
        context.debug_views['color_roi'] = vis
        context.metrics['color_ratio'] = float(best_ratio)
        context.outputs['color_name'] = best_name
        context.outputs['color_ratio'] = best_ratio
        context.add_detector_evidence('color', detector_evidence('color', status='OK' if best_name != 'unknown' else 'UNKNOWN', score=float(best_ratio), overlay_refs=['color_roi'], color_name=best_name, ratio=round(best_ratio, 6), contour_count=len(contours), roi_shape=list(roi.shape[:2])))
        min_ratio = float(config.get('min_ratio', 0.0))
        if best_ratio < min_ratio:
            context.warnings.append('blocking:color_ratio_below_threshold')


class QRDetector(DetectorBase):
    name = 'qr'
    config_key = 'qr'

    def run(self, context: PipelineContext, recipe: dict) -> None:
        config = self.config(recipe)
        roi = crop_roi(context.image, config.get('roi'))
        vis = roi.copy()
        detector = cv2.QRCodeDetector()
        value, points, _ = detector.detectAndDecode(roi)
        qr_points: list[list[int]] = []
        if points is not None and len(points):
            pts = points.astype(int).reshape(-1, 2)
            qr_points = pts.tolist()
            cv2.polylines(vis, [pts], True, (0, 255, 255), 2)
        context.debug_views['qr_roi'] = vis
        context.outputs['qr_ok'] = bool(value)
        context.outputs['qr_text'] = value or ''
        context.add_detector_evidence('qr', detector_evidence('qr', status='OK' if bool(value) else 'MISSING', score=1.0 if bool(value) else 0.0, overlay_refs=['qr_roi'] if qr_points else [], qr_ok=bool(value), qr_text=value or '', points=qr_points))


class ShapeDetector(DetectorBase):
    name = 'shape'
    config_key = 'shape'

    def run(self, context: PipelineContext, recipe: dict) -> None:
        config = self.config(recipe)
        roi = crop_roi(context.image, config.get('roi'))
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, th = cv2.threshold(gray, int(config.get('binary_thresh', 80)), 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        vis = cv2.cvtColor(th, cv2.COLOR_GRAY2BGR)
        if not contours:
            context.warnings.append('shape:no_contour')
            context.outputs['orientation_ok'] = False
            context.outputs['defect_type'] = 'NO_CONTOUR'
            context.add_detector_evidence('shape', detector_evidence('shape', status='NO_CONTOUR', score=0.0, warnings=['shape:no_contour']))
            return
        contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(contour)
        context.metrics['contour_area'] = float(area)
        cv2.drawContours(vis, [contour], -1, (0, 255, 0), 2)
        min_area = float(config.get('min_area', 1000))
        max_area = float(config.get('max_area', 1e9))
        low, high = config.get('aspect_ratio_range', [1.0, 2.5])
        rect = cv2.minAreaRect(contour)
        w, h = rect[1]
        short_side = max(1.0, min(w, h))
        long_side = max(w, h)
        ratio = float(long_side / short_side)
        shape_box = [float(v) for v in rect[0]] + [float(w), float(h), float(rect[2])]
        payload = {'contour_area': float(area), 'aspect_ratio': ratio, 'shape_box': shape_box}
        context.debug_views['shape_roi'] = vis
        if area < min_area or area > max_area:
            context.outputs['orientation_ok'] = False
            context.outputs['defect_type'] = 'AREA_OUT_OF_RANGE'
            context.add_detector_evidence('shape', detector_evidence('shape', status='AREA_OUT_OF_RANGE', score=0.0, warnings=['shape:area_out_of_range'], **payload))
            return
        if not (float(low) <= ratio <= float(high)):
            context.outputs['orientation_ok'] = False
            context.outputs['defect_type'] = 'BAD_ORIENTATION'
            context.add_detector_evidence('shape', detector_evidence('shape', status='BAD_ORIENTATION', score=0.0, warnings=['shape:bad_orientation'], **payload))
            return
        context.outputs['orientation_ok'] = True
        context.outputs['defect_type'] = 'NONE'
        context.add_detector_evidence('shape', detector_evidence('shape', status='OK', score=1.0, overlay_refs=['shape_roi'], **payload))


class NormalizeBrightnessStage(PipelineStage):
    name = 'normalize_brightness'

    def run(self, context: PipelineContext, recipe: dict) -> None:
        gray = cv2.cvtColor(context.image, cv2.COLOR_BGR2GRAY)
        mean_brightness = float(np.mean(gray))
        if 40.0 <= mean_brightness <= 220.0:
            return
        lab = cv2.cvtColor(context.image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        context.image = cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


REGISTRY = DetectorRegistry()
REGISTRY.register('color', ColorDetector, manifest=PluginManifest(kind='detector', name='color', capabilities=('COLOR_CLASSIFICATION',), runtime_truth='real', source='builtin', owner_plane='vision_processing', verification_requirements=('capture_process_decision_cycle',)))
REGISTRY.register('qr', QRDetector, manifest=PluginManifest(kind='detector', name='qr', capabilities=('QR_DECODE',), runtime_truth='real', source='builtin', owner_plane='vision_processing', verification_requirements=('capture_process_decision_cycle',)))
REGISTRY.register('shape', ShapeDetector, manifest=PluginManifest(kind='detector', name='shape', capabilities=('SHAPE_ANALYSIS', 'ORIENTATION_CHECK'), runtime_truth='real', source='builtin', owner_plane='vision_processing', verification_requirements=('capture_process_decision_cycle',)))


@dataclass(frozen=True, slots=True)
class CompiledVisionPipeline:
    """Hold a reusable pipeline plan derived from a recipe snapshot."""

    recipe_digest: str
    manager: PipelineManager

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable pipeline descriptor."""
        return {
            'recipe_digest': self.recipe_digest,
            'preprocessors': [stage.__class__.__name__ for stage in self.manager.preprocessors],
            'detectors': [detector.__class__.__name__ for detector in self.manager.detectors],
        }


def _normalize_recipe(recipe: dict | None) -> dict[str, object]:
    if not isinstance(recipe, dict):
        return {}
    return recipe


def _recipe_cache_payload(recipe: dict | None) -> str:
    normalized = _normalize_recipe(recipe)
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)


def _build_pipeline_uncached(recipe: dict | None = None) -> PipelineManager:
    recipe = _normalize_recipe(recipe)
    vision_cfg = recipe.get('vision', {}) if isinstance(recipe, dict) else {}
    manifest_plugins = vision_cfg.get('plugin_manifest') if isinstance(vision_cfg, dict) else None
    if manifest_plugins:
        REGISTRY.discover(manifest=manifest_plugins)
    elif vision_cfg.get('discover_entry_points', False):
        REGISTRY.discover()
    requested = vision_cfg.get('detector_order') or vision_cfg.get('enabled_detectors') or None
    return PipelineManager(
        preprocessors=[NormalizeBrightnessStage(), QualityStage()],
        detectors=REGISTRY.build(requested=requested),
    )


@lru_cache(maxsize=16)
def _compiled_pipeline_from_payload(recipe_payload: str) -> CompiledVisionPipeline:
    recipe = json.loads(recipe_payload) if recipe_payload else {}
    digest = sha1(recipe_payload.encode('utf-8')).hexdigest()[:12]
    return CompiledVisionPipeline(recipe_digest=digest, manager=_build_pipeline_uncached(recipe))


def compile_pipeline(recipe: dict | None = None) -> CompiledVisionPipeline:
    """Compile or retrieve a reusable detector pipeline for the given recipe.

    Args:
        recipe: Runtime recipe configuration.

    Returns:
        A cached pipeline plan keyed by the recipe content.
    """
    return _compiled_pipeline_from_payload(_recipe_cache_payload(recipe))


def clear_pipeline_cache() -> None:
    """Clear the compiled pipeline cache. Intended for tests and recipe reloads."""
    _compiled_pipeline_from_payload.cache_clear()


def compose_debug_view(image: np.ndarray, context: PipelineContext, summary: DetectionSummary) -> np.ndarray:
    vis = image.copy()
    overlay_lines = [
        f'item={summary.item_id} trace={summary.trace_id}',
        f'color={summary.color_name} ratio={summary.color_ratio:.2f}',
        f'qr_ok={summary.qr_ok} orient_ok={summary.orientation_ok} defect={summary.defect_type}',
        f'brightness={context.metrics.get("mean_brightness", 0.0):.1f} blur={context.metrics.get("blur_variance", 0.0):.1f}',
        f'score={summary.score:.3f}',
    ]
    for idx, line in enumerate(overlay_lines):
        color = (0, 255, 255) if idx == 0 else (0, 255, 0)
        cv2.putText(vis, line, (10, 30 + idx * 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
    return vis


def detector_manifest_catalog() -> list[dict[str, object]]:
    """Return detector plugin metadata exposed by the runtime registry."""
    return REGISTRY.manifest_catalog()

def build_pipeline(recipe: dict | None = None) -> PipelineManager:
    """Build a fresh pipeline instance for the provided recipe.

    Args:
        recipe: Runtime recipe configuration.

    Returns:
        A non-cached pipeline manager.
    """
    return _build_pipeline_uncached(recipe)


def process_frame(
    image: np.ndarray,
    recipe: dict,
    item_id: int = -1,
    batch_id: str = '',
    trace_id: str = '',
    *,
    pipeline: CompiledVisionPipeline | None = None,
    copy_input: bool = True,
) -> tuple[DetectionSummary, np.ndarray]:
    """Process a frame through the configured detector pipeline.

    Args:
        image: Input BGR image matrix.
        recipe: Runtime recipe configuration.
        item_id: Work item identifier.
        batch_id: Batch identifier.
        trace_id: Trace identifier.
        pipeline: Optional precompiled pipeline plan.
        copy_input: Whether to copy the input image before pipeline mutation.

    Returns:
        A detection summary and annotated visualization image.
    """
    context = PipelineContext(image=image.copy() if copy_input else image)
    compiled = pipeline or compile_pipeline(recipe)
    summary = compiled.manager.run(context, recipe, item_id=item_id, batch_id=batch_id, trace_id=trace_id)
    vis = compose_debug_view(context.image, context, summary)
    return summary, vis
