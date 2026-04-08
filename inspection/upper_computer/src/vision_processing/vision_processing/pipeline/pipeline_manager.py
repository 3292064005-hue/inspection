from __future__ import annotations

from .detector_runner import run_detectors
from .summary_builder import build_summary


class PipelineManager:
    def __init__(self, preprocessors: list[object], detectors: list[object]) -> None:
        self.preprocessors = list(preprocessors)
        self.detectors = list(detectors)

    def run(self, context, recipe: dict, *, item_id: int, batch_id: str, trace_id: str):
        for stage in self.preprocessors:
            stage.run(context, recipe)
        run_detectors(self.detectors, context, recipe)
        return build_summary(context, recipe, item_id=item_id, batch_id=batch_id, trace_id=trace_id)
