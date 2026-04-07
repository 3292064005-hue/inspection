from __future__ import annotations

from abc import ABC, abstractmethod


class PipelineStage(ABC):
    name = 'stage'

    @abstractmethod
    def run(self, context, recipe: dict) -> None:
        raise NotImplementedError
