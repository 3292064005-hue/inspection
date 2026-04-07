from __future__ import annotations

from pathlib import Path
from queue import Full

import cv2
import numpy as np

from vision_processing.artifact_writer import ArtifactWriter
from vision_processing.detectors import CompiledVisionPipeline, clear_pipeline_cache, compile_pipeline, process_frame
from vision_processing.pipeline.pipeline_manager import PipelineManager


def _demo_recipe() -> dict:
    return {
        'recipe_id': 'demo',
        'vision': {
            'quality': {'min_brightness': 0.0, 'max_brightness': 255.0, 'min_blur_variance': 0.0},
            'color': {
                'enabled': True,
                'roi': {'x': 0, 'y': 0, 'w': 320, 'h': 240},
                'hsv_ranges': {'red': [[0, 80, 80, 10, 255, 255], [170, 80, 80, 179, 255, 255]]},
                'min_ratio': 0.01,
            },
            'qr': {'enabled': False},
            'shape': {'enabled': False},
            'discover_entry_points': True,
        },
        'decision': {'expected_color': 'red'},
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }


def test_compile_pipeline_caches_recipe_build(monkeypatch) -> None:
    calls: list[dict] = []

    def _fake_build(recipe):
        calls.append(recipe)
        return PipelineManager(preprocessors=[], detectors=[])

    monkeypatch.setattr('vision_processing.detectors._build_pipeline_uncached', _fake_build)
    clear_pipeline_cache()
    recipe = _demo_recipe()
    first = compile_pipeline(recipe)
    second = compile_pipeline(recipe)
    assert isinstance(first, CompiledVisionPipeline)
    assert first is second
    assert len(calls) == 1


def test_process_frame_accepts_compiled_pipeline() -> None:
    clear_pipeline_cache()
    recipe = _demo_recipe()
    compiled = compile_pipeline(recipe)
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.rectangle(image, (60, 50), (260, 190), (0, 0, 255), -1)
    summary, vis = process_frame(image, recipe, item_id=1, batch_id='B', trace_id='T', pipeline=compiled)
    assert summary.color_name == 'red'
    assert vis.shape == image.shape
    assert compiled.to_dict()['recipe_digest']


def test_artifact_writer_persists_async_images(tmp_path: Path) -> None:
    writer = ArtifactWriter(max_queue_size=2)
    image = np.full((16, 16, 3), 255, dtype=np.uint8)
    target = tmp_path / 'images' / 'raw.png'
    receipt = writer.submit(target, image, kind='raw', trace_id='trace-1', item_id=1, batch_id='B1')
    assert receipt.status == 'queued'
    assert writer.flush(timeout_sec=2.0)
    writer.close(timeout_sec=2.0)
    assert target.exists()
    snapshot = writer.snapshot()
    assert snapshot['written'] >= 1
    assert snapshot['pending'] == 0
    assert snapshot['highWatermark'] >= 1


def test_artifact_writer_reports_queue_overload_without_sync_write(tmp_path: Path, monkeypatch) -> None:
    writer = ArtifactWriter(max_queue_size=1)
    image = np.zeros((8, 8, 3), dtype=np.uint8)

    def _raise_full(_task):
        raise Full

    monkeypatch.setattr(writer._queue, 'put_nowait', _raise_full)
    target = tmp_path / 'b.png'
    receipt = writer.submit(target, image, kind='annotated', trace_id='t2', item_id=2, batch_id='B')
    assert receipt.status == 'queue_overload'
    assert not target.exists()
    snapshot = writer.snapshot()
    assert snapshot['queueRejected'] >= 1
    assert snapshot['sync_fallback'] == 0
    writer.close(timeout_sec=2.0)
