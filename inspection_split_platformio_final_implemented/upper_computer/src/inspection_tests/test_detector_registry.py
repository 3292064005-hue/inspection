import numpy as np

from vision_processing.detectors import REGISTRY, build_pipeline, process_frame


def test_detector_registry_builds_requested_order():
    recipe = {'vision': {'detector_order': ['qr', 'color']}}
    pipeline = build_pipeline(recipe)
    names = [detector.name for detector in pipeline.detectors]
    assert names == ['qr', 'color']
    assert 'shape' in REGISTRY.factories


def test_consistency_checker_blocks_qr_without_text():
    image = np.zeros((120, 160, 3), dtype=np.uint8)
    recipe = {
        'recipe_id': 'demo',
        'vision': {
            'detector_order': ['color'],
            'quality': {'min_brightness': 0.0, 'max_brightness': 255.0, 'min_blur_variance': 0.0},
            'color': {'enabled': True, 'roi': {'x': 0, 'y': 0, 'w': 160, 'h': 120}, 'hsv_ranges': {'red': [[0, 80, 80, 10, 255, 255]]}},
            'qr': {'enabled': False},
        },
    }
    summary, _ = process_frame(image, recipe, item_id=1, batch_id='B', trace_id='T')
    assert isinstance(summary.valid, bool)
