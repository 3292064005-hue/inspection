from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Lock, Thread
import time
from typing import Any

import numpy as np

from inspection_utils.vision_common import save_image


@dataclass(slots=True)
class ArtifactWriteReceipt:
    """Describe how an artifact write request was accepted.

    Attributes:
        path: Absolute or workspace-relative file path planned for the artifact.
        status: Submission status. One of ``queued``, ``queue_overload``, or
            ``dropped_overload``.
        queue_depth: Queue depth immediately after submission.
        queue_usage: Fractional queue saturation at submission time.
        submitted_at_monotonic: Monotonic timestamp when the request was accepted.
    """

    path: str
    status: str
    queue_depth: int
    queue_usage: float
    submitted_at_monotonic: float

    def to_dict(self) -> dict[str, Any]:
        return {
            'path': self.path,
            'status': self.status,
            'queue_depth': self.queue_depth,
            'queueUsage': round(float(self.queue_usage), 4),
            'submitted_at_monotonic': round(self.submitted_at_monotonic, 6),
        }


@dataclass(slots=True)
class _ArtifactTask:
    path: str
    image: np.ndarray
    kind: str
    trace_id: str
    item_id: int
    batch_id: str
    submitted_at_monotonic: float


class ArtifactWriter:
    """Persist evidence images outside the synchronous vision hot path.

    The writer accepts image save requests and drains them from a background
    thread. When the queue is saturated, requests are rejected explicitly so the
    caller can degrade behavior without reintroducing synchronous disk I/O into
    the vision hot path. Metrics track queue watermarks, flush latency, and
    overload drops.
    """

    def __init__(self, *, max_queue_size: int = 32, worker_name: str = 'vision-artifact-writer', overload_threshold: float = 0.8) -> None:
        if int(max_queue_size) < 1:
            raise ValueError('max_queue_size must be >= 1')
        self._queue: Queue[_ArtifactTask] = Queue(maxsize=int(max_queue_size))
        self._stop_event = Event()
        self._lock = Lock()
        self._worker = Thread(target=self._run, name=worker_name, daemon=True)
        self._pending = 0
        self._written = 0
        self._failed = 0
        self._sync_fallback = 0
        self._dropped_overload = 0
        self._queue_rejected = 0
        self._last_error = ''
        self._closed = False
        self._high_watermark = 0
        self._max_queue_usage = 0.0
        self._flush_timeouts = 0
        self._last_flush_duration_ms = 0.0
        self._overload_threshold = max(0.05, min(1.0, float(overload_threshold)))
        self._worker.start()

    def submit(self, path: str | Path, image: np.ndarray, *, kind: str, trace_id: str, item_id: int, batch_id: str) -> ArtifactWriteReceipt:
        """Queue an artifact write without blocking the caller on disk I/O.

        Args:
            path: Target artifact path.
            image: Image payload to persist.
            kind: Logical artifact kind such as ``raw`` or ``annotated``.
            trace_id: Trace identifier used for diagnostics.
            item_id: Item identifier used for diagnostics.
            batch_id: Batch identifier used for diagnostics.

        Returns:
            Receipt describing whether the write was queued or rejected because
            the queue was already saturated.

        Raises:
            RuntimeError: If the writer has already been closed.
        """
        if self._closed:
            raise RuntimeError('artifact writer already closed')
        target_path = str(path)
        submitted_at = time.monotonic()
        task = _ArtifactTask(
            path=target_path,
            image=image,
            kind=str(kind),
            trace_id=str(trace_id),
            item_id=int(item_id),
            batch_id=str(batch_id),
            submitted_at_monotonic=submitted_at,
        )
        try:
            self._queue.put_nowait(task)
            with self._lock:
                self._pending += 1
                self._high_watermark = max(self._high_watermark, self._pending)
                queue_depth = self._pending
                queue_usage = self._queue_usage_unlocked()
                self._max_queue_usage = max(self._max_queue_usage, queue_usage)
            return ArtifactWriteReceipt(path=target_path, status='queued', queue_depth=queue_depth, queue_usage=queue_usage, submitted_at_monotonic=submitted_at)
        except Full:
            with self._lock:
                self._queue_rejected += 1
                queue_depth = self._pending
                queue_usage = self._queue_usage_unlocked()
                self._max_queue_usage = max(self._max_queue_usage, queue_usage)
            return ArtifactWriteReceipt(path=target_path, status='queue_overload', queue_depth=queue_depth, queue_usage=queue_usage, submitted_at_monotonic=submitted_at)

    def drop_overload(self, path: str | Path) -> ArtifactWriteReceipt:
        """Record a controlled overload drop without silently losing telemetry."""
        target_path = str(path)
        submitted_at = time.monotonic()
        with self._lock:
            self._dropped_overload += 1
            queue_depth = self._pending
            queue_usage = self._queue_usage_unlocked()
            self._max_queue_usage = max(self._max_queue_usage, queue_usage)
        return ArtifactWriteReceipt(path=target_path, status='dropped_overload', queue_depth=queue_depth, queue_usage=queue_usage, submitted_at_monotonic=submitted_at)

    def is_overloaded(self) -> bool:
        """Return whether the writer is currently above its backpressure threshold."""
        with self._lock:
            return self._queue_usage_unlocked() >= self._overload_threshold or self._queue_rejected > 0 or self._flush_timeouts > 0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            queue_usage = self._queue_usage_unlocked()
            overloaded = queue_usage >= self._overload_threshold or self._queue_rejected > 0 or self._flush_timeouts > 0
            return {
                'pending': self._pending,
                'written': self._written,
                'failed': self._failed,
                'sync_fallback': self._sync_fallback,
                'queueRejected': self._queue_rejected,
                'droppedOverload': self._dropped_overload,
                'last_error': self._last_error,
                'closed': self._closed,
                'queue_capacity': self._queue.maxsize,
                'queueUsage': round(queue_usage, 4),
                'highWatermark': self._high_watermark,
                'maxQueueUsage': round(self._max_queue_usage, 4),
                'flushTimeouts': self._flush_timeouts,
                'lastFlushDurationMs': round(self._last_flush_duration_ms, 3),
                'overloaded': overloaded,
                'overloadThreshold': round(self._overload_threshold, 4),
            }

    def flush(self, *, timeout_sec: float = 5.0) -> bool:
        started = time.monotonic()
        deadline = started + max(0.0, float(timeout_sec))
        while time.monotonic() <= deadline:
            with self._lock:
                if self._pending <= 0:
                    self._last_flush_duration_ms = (time.monotonic() - started) * 1000.0
                    return True
            time.sleep(0.01)
        with self._lock:
            self._last_flush_duration_ms = (time.monotonic() - started) * 1000.0
            if self._pending > 0:
                self._flush_timeouts += 1
            return self._pending <= 0

    def close(self, *, timeout_sec: float = 5.0) -> None:
        if self._closed:
            return
        self.flush(timeout_sec=timeout_sec)
        self._closed = True
        self._stop_event.set()
        self._worker.join(timeout=max(0.1, float(timeout_sec)))

    def _run(self) -> None:
        while not self._stop_event.is_set() or not self._queue.empty():
            try:
                task = self._queue.get(timeout=0.05)
            except Empty:
                continue
            try:
                save_image(task.path, task.image)
                with self._lock:
                    self._written += 1
            except Exception as exc:  # pragma: no cover - defensive I/O guard
                with self._lock:
                    self._failed += 1
                    self._last_error = str(exc)
            finally:
                with self._lock:
                    self._pending = max(0, self._pending - 1)
                self._queue.task_done()

    def _queue_usage_unlocked(self) -> float:
        capacity = max(1, int(self._queue.maxsize))
        return min(1.0, float(self._pending) / float(capacity))
