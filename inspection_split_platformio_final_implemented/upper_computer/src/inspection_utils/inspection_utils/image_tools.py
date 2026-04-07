from __future__ import annotations

from pathlib import Path
import cv2
import numpy as np


def crop_roi(image: np.ndarray, roi: dict | None) -> np.ndarray:
    if not roi:
        return image.copy()
    height, width = image.shape[:2]
    x = max(0, int(roi['x']))
    y = max(0, int(roi['y']))
    w = max(1, int(roi['w']))
    h = max(1, int(roi['h']))
    x2 = min(width, x + w)
    y2 = min(height, y + h)
    if x >= width or y >= height or x2 <= x or y2 <= y:
        return image.copy()
    return image[y:y2, x:x2].copy()


def save_image(path: str | Path, image: np.ndarray) -> str:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(p), image)
    return str(p)
