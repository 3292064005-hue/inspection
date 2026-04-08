import numpy as np
import cv2

from vision_processing.detectors import process_frame


def test_process_frame_pipeline_returns_evidence_structure():
    image = np.zeros((240, 320, 3), dtype=np.uint8)
    cv2.rectangle(image, (60, 50), (260, 190), (0, 0, 255), -1)
    recipe = {
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
        },
        'decision': {'expected_color': 'red'},
        'sort_mapping': {'OK': 1, 'NG': 2, 'RECHECK': 3},
    }
    summary, vis = process_frame(image, recipe, item_id=1, batch_id='B', trace_id='T')
    assert summary.color_name == 'red'
    assert 'detectors' in summary.evidence
    assert 'color' in summary.evidence['detectors']
    assert vis.shape == image.shape
