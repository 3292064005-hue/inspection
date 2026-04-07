from __future__ import annotations

import time


class BridgeWatchdog:
    def __init__(self, timeout_sec: float = 0.0) -> None:
        self.timeout_sec = float(timeout_sec)
        self._last_seen = time.monotonic()
        self._armed = self.timeout_sec > 0.0

    def observe(self) -> None:
        self._last_seen = time.monotonic()

    def arm(self, timeout_sec: float | None = None) -> None:
        if timeout_sec is not None:
            self.timeout_sec = float(timeout_sec)
        self._armed = self.timeout_sec > 0.0
        self.observe()

    def expired(self) -> bool:
        if not self._armed or self.timeout_sec <= 0.0:
            return False
        return (time.monotonic() - self._last_seen) > self.timeout_sec
