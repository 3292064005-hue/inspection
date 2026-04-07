from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

import cv2
import numpy as np


@dataclass(slots=True)
class CameraProviderMetrics:
    """Runtime health snapshot for camera providers.

    Attributes:
        connected: Whether the underlying capture backend is currently usable.
        reconnect_count: Number of reconnect attempts already executed.
        reconnect_failures: Number of reconnect attempts that failed to re-open.
        read_failures: Number of failed frame reads.
        consecutive_failures: Consecutive failed reads since the last good frame.
        frames_read: Number of successfully produced frames.
        last_frame_monotonic: Monotonic timestamp of the last successful frame.
        last_open_monotonic: Monotonic timestamp of the last open attempt.
        last_reconnect_monotonic: Monotonic timestamp of the last reconnect attempt.
        last_error: Last observed backend error.
        provider: Provider identifier.
        stale_frame_ms: Explicit stale age override used by tests or fallback code.
        release_failures: Number of capture release failures.
        status_reason: Human-readable status reason used by diagnostics.
    """

    connected: bool = False
    reconnect_count: int = 0
    reconnect_failures: int = 0
    read_failures: int = 0
    consecutive_failures: int = 0
    frames_read: int = 0
    last_frame_monotonic: float = 0.0
    last_open_monotonic: float = 0.0
    last_reconnect_monotonic: float = 0.0
    last_error: str = ''
    provider: str = 'opencv'
    stale_frame_ms: float = 0.0
    release_failures: int = 0
    status_reason: str = 'initializing'

    def to_dict(self, *, now: float | None = None) -> dict[str, object]:
        """Return a diagnostics-friendly dictionary.

        Args:
            now: Optional monotonic timestamp override used by tests.

        Returns:
            A serialisable health payload.

        Raises:
            This method does not raise by design.

        Boundary behavior:
            When no successful frame has been read yet, ``staleFrameMs`` falls
            back to ``stale_frame_ms`` instead of deriving from monotonic time.
        """

        current = float(now if now is not None else time.monotonic())
        stale_ms = float(self.stale_frame_ms)
        if self.last_frame_monotonic > 0.0:
            stale_ms = max(0.0, (current - self.last_frame_monotonic) * 1000.0)
        return {
            'connected': bool(self.connected),
            'reconnectCount': int(self.reconnect_count),
            'reconnectFailures': int(self.reconnect_failures),
            'readFailures': int(self.read_failures),
            'consecutiveFailures': int(self.consecutive_failures),
            'framesRead': int(self.frames_read),
            'lastFrameMonotonic': float(self.last_frame_monotonic),
            'lastOpenMonotonic': float(self.last_open_monotonic),
            'lastReconnectMonotonic': float(self.last_reconnect_monotonic),
            'lastError': str(self.last_error),
            'provider': str(self.provider),
            'staleFrameMs': round(float(stale_ms), 3),
            'releaseFailures': int(self.release_failures),
            'statusReason': str(self.status_reason),
        }


class BaseCameraProvider:
    def open(self) -> bool:
        raise NotImplementedError

    def read(self) -> tuple[bool, np.ndarray | None]:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def health(self) -> dict[str, object]:
        raise NotImplementedError


class MockCameraProvider(BaseCameraProvider):
    def __init__(self, frame_factory: Callable[[], np.ndarray]) -> None:
        self.frame_factory = frame_factory
        self.metrics = CameraProviderMetrics(connected=True, provider='mock', status_reason='mock_ready')

    def open(self) -> bool:
        self.metrics.connected = True
        self.metrics.last_open_monotonic = time.monotonic()
        self.metrics.status_reason = 'mock_ready'
        return True

    def read(self) -> tuple[bool, np.ndarray | None]:
        try:
            frame = self.frame_factory()
        except Exception as exc:
            self.metrics.connected = False
            self.metrics.read_failures += 1
            self.metrics.consecutive_failures += 1
            self.metrics.last_error = str(exc)
            self.metrics.status_reason = 'mock_frame_factory_failed'
            return False, None
        self.metrics.connected = True
        self.metrics.frames_read += 1
        self.metrics.consecutive_failures = 0
        self.metrics.last_frame_monotonic = time.monotonic()
        self.metrics.last_error = ''
        self.metrics.status_reason = 'mock_frame_ok'
        return True, frame

    def close(self) -> None:
        self.metrics.connected = False
        self.metrics.status_reason = 'mock_closed'

    def health(self) -> dict[str, object]:
        payload = self.metrics.to_dict()
        payload['stale'] = False
        payload['staleThresholdMs'] = 0.0
        return payload


class OpenCVCameraProvider(BaseCameraProvider):
    """OpenCV-backed camera provider with bounded reconnect behavior.

    Args:
        camera_index: Camera device index passed to OpenCV.
        frame_width: Requested capture width.
        frame_height: Requested capture height.
        capture_factory: Optional dependency injection for tests.
        reconnect_backoff_sec: Sleep interval before reconnect attempts.
        max_reconnect_attempts: Maximum reconnect attempts after a failed read.
        stale_frame_threshold_ms: Threshold above which the provider reports a
            stale frame stream.

    Returns:
        None.

    Raises:
        This constructor does not raise by design. Backend failures are exposed
        through ``open()``, ``read()``, and ``health()``.

    Boundary behavior:
        Negative reconnect/backoff values are clamped to safe lower bounds.
    """

    def __init__(
        self,
        *,
        camera_index: int,
        frame_width: int,
        frame_height: int,
        capture_factory: Callable[[int], Any] | None = None,
        reconnect_backoff_sec: float = 0.05,
        max_reconnect_attempts: int = 2,
        stale_frame_threshold_ms: float = 1000.0,
    ) -> None:
        self.camera_index = int(camera_index)
        self.frame_width = int(frame_width)
        self.frame_height = int(frame_height)
        self.capture_factory = capture_factory or cv2.VideoCapture
        self.reconnect_backoff_sec = max(0.0, float(reconnect_backoff_sec))
        self.max_reconnect_attempts = max(0, int(max_reconnect_attempts))
        self.stale_frame_threshold_ms = max(0.0, float(stale_frame_threshold_ms))
        self.metrics = CameraProviderMetrics(provider='opencv')
        self._capture: Any | None = None

    def _configure_capture(self, capture: Any) -> None:
        try:
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        except Exception:
            # Configuration failure is non-fatal because many virtual/test
            # captures do not expose these OpenCV properties.
            pass

    def open(self) -> bool:
        """Open the capture backend.

        Returns:
            ``True`` when the capture backend reports an opened state.

        Raises:
            This method never raises backend errors; failures are converted into
            metrics for diagnostics.

        Boundary behavior:
            If the previous capture cannot be released cleanly, the provider
            still proceeds with a new open attempt while incrementing
            ``release_failures``.
        """

        self.close()
        self.metrics.last_open_monotonic = time.monotonic()
        self.metrics.status_reason = 'opening'
        try:
            capture = self.capture_factory(self.camera_index)
        except Exception as exc:
            self.metrics.connected = False
            self.metrics.last_error = str(exc)
            self.metrics.status_reason = 'camera_open_exception'
            return False
        self._capture = capture
        self._configure_capture(capture)
        opened = bool(getattr(capture, 'isOpened', lambda: True)())
        self.metrics.connected = opened
        self.metrics.last_error = '' if opened else 'camera_open_failed'
        self.metrics.status_reason = 'camera_ready' if opened else 'camera_open_failed'
        return opened

    def _reconnect(self) -> bool:
        self.metrics.reconnect_count += 1
        self.metrics.last_reconnect_monotonic = time.monotonic()
        self.metrics.status_reason = 'reconnecting'
        self.close()
        if self.reconnect_backoff_sec > 0:
            time.sleep(self.reconnect_backoff_sec)
        reopened = self.open()
        if not reopened:
            self.metrics.reconnect_failures += 1
            self.metrics.status_reason = 'reconnect_failed'
        return reopened

    def read(self) -> tuple[bool, np.ndarray | None]:
        """Read one frame from the capture backend.

        Returns:
            Tuple ``(ok, frame)`` where ``ok`` indicates whether a usable frame
            was produced.

        Raises:
            Backend exceptions are captured and converted into metrics.

        Boundary behavior:
            When the capture is absent, the provider attempts ``open()`` first.
            After a failed read, reconnect attempts are bounded by
            ``max_reconnect_attempts``.
        """

        if self._capture is None and not self.open():
            self.metrics.read_failures += 1
            self.metrics.consecutive_failures += 1
            self.metrics.status_reason = 'camera_open_before_read_failed'
            return False, None

        for attempt in range(self.max_reconnect_attempts + 1):
            capture = self._capture
            try:
                ok, frame = capture.read() if capture is not None else (False, None)
            except Exception as exc:
                ok, frame = False, None
                self.metrics.last_error = str(exc)
                self.metrics.status_reason = 'camera_read_exception'
            if ok and frame is not None:
                self.metrics.connected = True
                self.metrics.consecutive_failures = 0
                self.metrics.frames_read += 1
                self.metrics.last_frame_monotonic = time.monotonic()
                self.metrics.last_error = ''
                self.metrics.stale_frame_ms = 0.0
                self.metrics.status_reason = 'camera_frame_ok'
                return True, frame
            self.metrics.read_failures += 1
            self.metrics.consecutive_failures += 1
            self.metrics.connected = False
            if not self.metrics.last_error:
                self.metrics.last_error = 'camera_read_failed'
            if self.metrics.status_reason not in {'camera_read_exception', 'reconnect_failed'}:
                self.metrics.status_reason = 'camera_read_failed'
            if attempt >= self.max_reconnect_attempts:
                break
            self._reconnect()
        return False, None

    def close(self) -> None:
        capture = self._capture
        self._capture = None
        if capture is not None:
            try:
                capture.release()
            except Exception:
                self.metrics.release_failures += 1
        self.metrics.connected = False
        if self.metrics.status_reason not in {'camera_open_failed', 'reconnect_failed'}:
            self.metrics.status_reason = 'camera_closed'

    def health(self) -> dict[str, object]:
        payload = self.metrics.to_dict()
        stale_ms = float(payload.get('staleFrameMs', 0.0) or 0.0)
        payload['stale'] = bool(self.metrics.frames_read > 0 and stale_ms > self.stale_frame_threshold_ms)
        payload['staleThresholdMs'] = float(self.stale_frame_threshold_ms)
        if payload['stale'] and str(payload.get('statusReason', '')) == 'camera_frame_ok':
            payload['statusReason'] = 'camera_frame_stale'
        return payload



class Esp32HttpCameraProvider(BaseCameraProvider):
    """HTTP snapshot-based camera provider for ESP32-S3 camera modules.

    The provider polls a JPEG snapshot endpoint instead of opening a local
    capture device. This keeps the upstream ROS topic contract unchanged while
    allowing the upper computer to consume an ESP32-S3 camera stream over Wi-Fi.

    Args:
        base_url: Base URL of the ESP32-S3 camera service.
        snapshot_path: Relative path of the JPEG snapshot endpoint.
        health_path: Relative path of the JSON health endpoint.
        request_timeout_ms: HTTP timeout for snapshot and health requests.
        stale_frame_threshold_ms: Threshold above which the provider reports a
            stale frame stream.
        byte_fetcher: Optional byte-fetcher injection used by tests.
        json_fetcher: Optional JSON fetcher injection used by tests.
        auth_header: Optional HTTP header used for token authentication.
        auth_token: Optional shared token attached to health/snapshot requests.

    Returns:
        None.

    Raises:
        Constructor errors are not raised by design. Connectivity failures are
        surfaced through ``open()``, ``read()``, and ``health()``.

    Boundary behavior:
        Health endpoint failures are tolerated; the provider will continue using
        the latest locally-known metrics and mark the health reason accordingly.
    """

    def __init__(
        self,
        *,
        base_url: str,
        snapshot_path: str = '/api/v1/camera/snapshot',
        health_path: str = '/api/v1/camera/health',
        request_timeout_ms: float = 1200.0,
        stale_frame_threshold_ms: float = 1000.0,
        byte_fetcher: Callable[[str, float], bytes] | None = None,
        json_fetcher: Callable[..., dict[str, object]] | None = None,
        auth_header: str = 'X-Inspection-Token',
        auth_token: str = '',
    ) -> None:
        self.base_url = str(base_url).rstrip('/') + '/'
        self.snapshot_path = '/' + str(snapshot_path).lstrip('/')
        self.health_path = '/' + str(health_path).lstrip('/')
        self.request_timeout_sec = max(0.05, float(request_timeout_ms) / 1000.0)
        self.stale_frame_threshold_ms = max(0.0, float(stale_frame_threshold_ms))
        self.metrics = CameraProviderMetrics(provider='esp32_http', status_reason='esp32_http_initializing')
        self._fetch_bytes = byte_fetcher or self._default_fetch_bytes
        self._fetch_json = json_fetcher or self._default_fetch_json
        self.auth_header = str(auth_header or 'X-Inspection-Token').strip()
        self.auth_token = str(auth_token or '').strip()
        self._last_remote_health: dict[str, object] = {}

    def _url(self, relative_path: str) -> str:
        return urljoin(self.base_url, relative_path.lstrip('/'))

    def _request_headers(self) -> dict[str, str]:
        if not self.auth_token:
            return {}
        return {self.auth_header: self.auth_token}

    def _invoke_fetcher(self, fetcher: Callable[..., Any], url: str) -> Any:
        headers = self._request_headers()
        if headers:
            try:
                return fetcher(url, self.request_timeout_sec, headers)
            except TypeError:
                # Backward compatibility for two-argument test doubles.
                pass
        return fetcher(url, self.request_timeout_sec)

    def _default_fetch_bytes(self, url: str, timeout_sec: float, headers: dict[str, str] | None = None) -> bytes:
        request = Request(url, headers=dict(headers or {}))
        with urlopen(request, timeout=timeout_sec) as response:  # nosec B310 - controlled local device URL
            return response.read()

    def _default_fetch_json(self, url: str, timeout_sec: float, headers: dict[str, str] | None = None) -> dict[str, object]:
        raw = self._default_fetch_bytes(url, timeout_sec, headers)
        decoded = json.loads(raw.decode('utf-8')) if raw else {}
        return decoded if isinstance(decoded, dict) else {}

    def open(self) -> bool:
        """Probe the remote ESP32-S3 snapshot or health endpoint.

        Returns:
            ``True`` when the remote endpoint is reachable.

        Raises:
            This method converts HTTP and decode errors into metrics and does
            not raise them to callers.

        Boundary behavior:
            When the health endpoint is unavailable but the snapshot endpoint
            responds, the provider still transitions to the connected state.
        """

        self.metrics.last_open_monotonic = time.monotonic()
        try:
            self._last_remote_health = self._invoke_fetcher(self._fetch_json, self._url(self.health_path))
            self.metrics.connected = True
            self.metrics.last_error = ''
            self.metrics.status_reason = 'esp32_health_ok'
            return True
        except Exception as exc:
            self.metrics.last_error = str(exc)
            self.metrics.status_reason = 'esp32_health_probe_failed'
        try:
            payload = self._invoke_fetcher(self._fetch_bytes, self._url(self.snapshot_path))
            if payload:
                self.metrics.connected = True
                self.metrics.last_error = ''
                self.metrics.status_reason = 'esp32_snapshot_probe_ok'
                return True
        except Exception as exc:
            self.metrics.last_error = str(exc)
            self.metrics.status_reason = 'esp32_snapshot_probe_failed'
        self.metrics.connected = False
        return False

    def read(self) -> tuple[bool, np.ndarray | None]:
        """Fetch and decode one JPEG snapshot from the ESP32-S3.

        Returns:
            Tuple ``(ok, frame)`` where ``frame`` is a BGR ``numpy.ndarray`` on
            success.

        Raises:
            HTTP and decode failures are converted into provider metrics.

        Boundary behavior:
            Invalid JPEG payloads are treated as read failures and do not update
            ``last_frame_monotonic``.
        """

        if not self.metrics.connected and not self.open():
            self.metrics.read_failures += 1
            self.metrics.consecutive_failures += 1
            self.metrics.status_reason = 'esp32_snapshot_read_failed'
            return False, None

        try:
            payload = self._invoke_fetcher(self._fetch_bytes, self._url(self.snapshot_path))
            image = cv2.imdecode(np.frombuffer(payload, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError('esp32_snapshot_decode_failed')
            self.metrics.connected = True
            self.metrics.consecutive_failures = 0
            self.metrics.frames_read += 1
            self.metrics.last_frame_monotonic = time.monotonic()
            self.metrics.last_error = ''
            self.metrics.stale_frame_ms = 0.0
            self.metrics.status_reason = 'esp32_frame_ok'
            try:
                self._last_remote_health = self._invoke_fetcher(self._fetch_json, self._url(self.health_path))
            except Exception as exc:
                self.metrics.status_reason = 'esp32_frame_ok_health_stale'
                self.metrics.last_error = str(exc)
            return True, image
        except Exception as exc:
            self.metrics.connected = False
            self.metrics.read_failures += 1
            self.metrics.consecutive_failures += 1
            self.metrics.last_error = str(exc)
            self.metrics.status_reason = 'esp32_snapshot_read_failed'
            return False, None

    def close(self) -> None:
        self.metrics.connected = False
        if self.metrics.status_reason not in {'esp32_snapshot_probe_failed', 'esp32_health_probe_failed'}:
            self.metrics.status_reason = 'esp32_http_closed'

    def health(self) -> dict[str, object]:
        payload = self.metrics.to_dict()
        stale_ms = float(payload.get('staleFrameMs', 0.0) or 0.0)
        payload['stale'] = bool(self.metrics.frames_read > 0 and stale_ms > self.stale_frame_threshold_ms)
        payload['staleThresholdMs'] = float(self.stale_frame_threshold_ms)
        if payload['stale'] and str(payload.get('statusReason', '')) in {'esp32_frame_ok', 'esp32_frame_ok_health_stale'}:
            payload['statusReason'] = 'esp32_frame_stale'
        if self._last_remote_health:
            payload['remoteHealth'] = dict(self._last_remote_health)
        payload['snapshotUrl'] = self._url(self.snapshot_path)
        payload['healthUrl'] = self._url(self.health_path)
        payload['authEnabled'] = bool(self.auth_token)
        payload['authHeader'] = self.auth_header if self.auth_token else ''
        return payload
