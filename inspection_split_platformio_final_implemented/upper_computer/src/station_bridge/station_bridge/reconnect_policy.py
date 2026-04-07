from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ReconnectPolicy:
    base_delay_sec: float = 0.5
    max_delay_sec: float = 5.0

    def delay_for_attempt(self, attempt: int) -> float:
        if attempt <= 0:
            return self.base_delay_sec
        delay = self.base_delay_sec * (2 ** max(0, attempt - 1))
        return min(self.max_delay_sec, delay)
