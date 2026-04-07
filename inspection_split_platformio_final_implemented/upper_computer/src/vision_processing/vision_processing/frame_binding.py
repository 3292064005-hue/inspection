from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class FrameSample:
    frame_index: int
    monotonic_ts: float
    stamp: Any
    header: Any
    image: Any


@dataclass(slots=True)
class CaptureRequestBinding:
    request: dict[str, Any]
    monotonic_ts: float


class FrameBindingBuffer:
    """Bind capture requests to camera frames with bounded pending state.

    Args:
        max_frames: Number of recent frames retained for explicit or fallback binding.
        fallback_window_sec: Maximum age window for reusing the latest cached frame.
        max_pending_requests: Maximum queued capture requests waiting for a future frame.
        pending_overload_policy: Overflow handling policy. ``drop_oldest`` keeps the
            freshest requests, while ``drop_newest`` preserves existing queued work.
    """

    def __init__(self, *, max_frames: int = 8, fallback_window_sec: float = 0.25, max_pending_requests: int = 32, pending_overload_policy: str = 'drop_oldest') -> None:
        self.frames: deque[FrameSample] = deque(maxlen=max_frames)
        self.pending: deque[CaptureRequestBinding] = deque()
        self.last_consumed_frame_index = -1
        self.fallback_window_sec = max(0.0, float(fallback_window_sec))
        self.max_pending_requests = max(1, int(max_pending_requests))
        policy = str(pending_overload_policy or 'drop_oldest').strip().lower()
        self.pending_overload_policy = policy if policy in {'drop_oldest', 'drop_newest'} else 'drop_oldest'
        self.last_submit_status = 'idle'

    def push_frame(self, frame: FrameSample) -> list[tuple[dict[str, Any], FrameSample]]:
        self.frames.append(frame)
        ready: list[tuple[dict[str, Any], FrameSample]] = []
        while self.pending:
            request = self.pending[0]
            bound = self.try_bind(request.request, request_monotonic=request.monotonic_ts)
            if bound is None:
                break
            self.pending.popleft()
            ready.append((request.request, bound))
        return ready

    def submit_request(self, request: dict[str, Any], *, monotonic_ts: float) -> FrameSample | None:
        bound = self.try_bind(request, request_monotonic=monotonic_ts)
        if bound is not None:
            self.last_submit_status = 'bound'
            return bound
        binding = CaptureRequestBinding(request=request, monotonic_ts=monotonic_ts)
        if len(self.pending) >= self.max_pending_requests:
            if self.pending_overload_policy == 'drop_newest':
                self.last_submit_status = 'drop_newest'
                return None
            self.pending.popleft()
            self.last_submit_status = 'drop_oldest'
        else:
            self.last_submit_status = 'queued'
        self.pending.append(binding)
        return None

    def try_bind(self, request: dict[str, Any], *, request_monotonic: float) -> FrameSample | None:
        explicit_frame_index = request.get('frame_index')
        if explicit_frame_index is not None:
            try:
                explicit_frame_index = int(explicit_frame_index)
            except Exception:
                explicit_frame_index = None
        candidates = list(self.frames)
        if explicit_frame_index is not None:
            for frame in candidates:
                if frame.frame_index == explicit_frame_index and frame.frame_index > self.last_consumed_frame_index:
                    self.last_consumed_frame_index = frame.frame_index
                    return frame
            return None
        for frame in candidates:
            if frame.frame_index <= self.last_consumed_frame_index:
                continue
            if frame.monotonic_ts >= request_monotonic:
                self.last_consumed_frame_index = frame.frame_index
                return frame
        allow_cached_frame = bool(request.get('allow_cached_frame', False))
        latest = candidates[-1] if candidates else None
        if not allow_cached_frame or latest is None or latest.frame_index <= self.last_consumed_frame_index:
            return None
        if request_monotonic - latest.monotonic_ts <= self.fallback_window_sec:
            self.last_consumed_frame_index = latest.frame_index
            return latest
        return None
