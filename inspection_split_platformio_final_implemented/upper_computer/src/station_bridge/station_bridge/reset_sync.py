from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass(slots=True)
class ResetSync:
    pending: bool = False
    requested_at: float = 0.0
    seq: int = -1

    def start(self, seq: int) -> None:
        self.pending = True
        self.requested_at = time.monotonic()
        self.seq = seq

    def complete(self) -> None:
        self.pending = False
        self.requested_at = 0.0
        self.seq = -1

    def snapshot(self) -> dict[str, object]:
        return {'pending': self.pending, 'requested_at': round(self.requested_at, 6), 'seq': self.seq}
