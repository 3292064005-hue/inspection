from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from typing import Any

from inspection_utils.protocol import Frame, FrameStreamParser


class RXParser:
    def __init__(self, duplicate_window_sec: float = 1.5, max_seen: int = 128) -> None:
        self._parser = FrameStreamParser()
        self.duplicate_window_sec = float(duplicate_window_sec)
        self._seen: deque[tuple[str, float]] = deque(maxlen=max_seen)

    def _payload_signature(self, payload: bytes) -> tuple[str, str]:
        digest = hashlib.sha1(payload).hexdigest()[:12] if payload else 'empty'
        device_id = ''
        if payload:
            try:
                decoded: Any = json.loads(payload.decode('utf-8'))
                if isinstance(decoded, dict):
                    device_id = str(decoded.get('device_id', ''))
            except Exception:
                device_id = ''
        return device_id, digest

    def _dedup_key(self, frame: Frame) -> str:
        device_id, digest = self._payload_signature(frame.payload)
        return f'{device_id}|{frame.cmd}|{frame.seq}|{digest}'

    def feed(self, chunk: bytes) -> list[Frame]:
        fresh: list[Frame] = []
        now = time.monotonic()
        for frame in self._parser.feed(chunk):
            key = self._dedup_key(frame)
            if any(existing == key and (now - ts) <= self.duplicate_window_sec for existing, ts in self._seen):
                continue
            self._seen.append((key, now))
            fresh.append(frame)
        return fresh
