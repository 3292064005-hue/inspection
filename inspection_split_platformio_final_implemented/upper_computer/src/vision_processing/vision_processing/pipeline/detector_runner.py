from __future__ import annotations

from typing import Iterable


def run_detectors(detectors: Iterable[object], context, recipe: dict) -> None:
    for detector in detectors:
        if hasattr(detector, 'enabled') and not detector.enabled(recipe):
            continue
        detector.run(context, recipe)
