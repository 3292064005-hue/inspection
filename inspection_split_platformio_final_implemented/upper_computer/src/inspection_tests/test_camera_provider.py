from __future__ import annotations

import cv2
import numpy as np

from vision_acquisition.camera_provider import Esp32HttpCameraProvider, MockCameraProvider, OpenCVCameraProvider


class _Capture:
    def __init__(self, reads):
        self.reads = list(reads)
        self.released = False

    def isOpened(self):
        return True

    def set(self, *_args):
        return True

    def read(self):
        if not self.reads:
            return False, None
        item = self.reads.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def release(self):
        self.released = True


class _BrokenReleaseCapture(_Capture):
    def release(self):
        raise RuntimeError('release_failed')


def test_mock_camera_provider_reports_health() -> None:
    provider = MockCameraProvider(lambda: np.zeros((4, 4, 3), dtype=np.uint8))
    assert provider.open() is True
    ok, frame = provider.read()
    assert ok is True
    assert frame is not None
    health = provider.health()
    assert health['provider'] == 'mock'
    assert health['framesRead'] == 1
    assert health['statusReason'] == 'mock_frame_ok'



def test_opencv_camera_provider_reconnects_after_read_failure() -> None:
    captures = [_Capture([(False, None)]), _Capture([(True, np.zeros((2, 2, 3), dtype=np.uint8))])]
    provider = OpenCVCameraProvider(
        camera_index=0,
        frame_width=2,
        frame_height=2,
        capture_factory=lambda _index: captures.pop(0),
        reconnect_backoff_sec=0.0,
        max_reconnect_attempts=1,
        stale_frame_threshold_ms=1.0,
    )
    ok, frame = provider.read()
    assert ok is True
    assert frame is not None
    health = provider.health()
    assert health['reconnectCount'] == 1
    assert health['readFailures'] >= 1
    assert health['statusReason'] == 'camera_frame_ok'



def test_opencv_camera_provider_marks_stale_health() -> None:
    provider = OpenCVCameraProvider(
        camera_index=0,
        frame_width=2,
        frame_height=2,
        capture_factory=lambda _index: _Capture([(True, np.zeros((2, 2, 3), dtype=np.uint8))]),
        reconnect_backoff_sec=0.0,
        max_reconnect_attempts=0,
        stale_frame_threshold_ms=1.0,
    )
    provider.open()
    ok, _frame = provider.read()
    assert ok is True
    provider.metrics.last_frame_monotonic = 0.0
    provider.metrics.stale_frame_ms = 5.0
    health = provider.health()
    assert health['connected'] is True
    assert health['stale'] is True
    assert health['statusReason'] == 'camera_frame_stale'



def test_opencv_camera_provider_reports_reconnect_failure_when_reopen_fails() -> None:
    captures = [_Capture([(False, None)])]

    def _factory(_index: int):
        if captures:
            return captures.pop(0)
        raise RuntimeError('reopen_failed')

    provider = OpenCVCameraProvider(
        camera_index=0,
        frame_width=2,
        frame_height=2,
        capture_factory=_factory,
        reconnect_backoff_sec=0.0,
        max_reconnect_attempts=1,
        stale_frame_threshold_ms=1.0,
    )

    ok, frame = provider.read()
    assert ok is False
    assert frame is None
    health = provider.health()
    assert health['reconnectCount'] == 1
    assert health['reconnectFailures'] == 1
    assert health['statusReason'] == 'reconnect_failed'



def test_opencv_camera_provider_tracks_release_failures() -> None:
    provider = OpenCVCameraProvider(
        camera_index=0,
        frame_width=2,
        frame_height=2,
        capture_factory=lambda _index: _BrokenReleaseCapture([(True, np.zeros((2, 2, 3), dtype=np.uint8))]),
        reconnect_backoff_sec=0.0,
        max_reconnect_attempts=0,
        stale_frame_threshold_ms=1.0,
    )
    assert provider.open() is True
    provider.close()
    health = provider.health()
    assert health['releaseFailures'] == 1
    assert health['connected'] is False


def test_esp32_http_camera_provider_reads_snapshot_and_health() -> None:
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    ok, encoded = cv2.imencode('.jpg', frame)
    assert ok is True

    provider = Esp32HttpCameraProvider(
        base_url='http://device.local',
        snapshot_path='/api/v1/camera/snapshot',
        health_path='/api/v1/camera/health',
        request_timeout_ms=100.0,
        stale_frame_threshold_ms=1.0,
        byte_fetcher=lambda url, timeout: encoded.tobytes(),
        json_fetcher=lambda url, timeout: {'deviceId': 'esp32-cam-01', 'cameraOk': True},
    )

    assert provider.open() is True
    ok, image = provider.read()
    assert ok is True
    assert image is not None
    health = provider.health()
    assert health['provider'] == 'esp32_http'
    assert health['remoteHealth']['deviceId'] == 'esp32-cam-01'
    assert health['snapshotUrl'].endswith('/api/v1/camera/snapshot')


def test_esp32_http_camera_provider_reports_snapshot_failure() -> None:
    provider = Esp32HttpCameraProvider(
        base_url='http://device.local',
        request_timeout_ms=100.0,
        stale_frame_threshold_ms=1.0,
        byte_fetcher=lambda url, timeout: (_ for _ in ()).throw(RuntimeError('snapshot_failed')),
        json_fetcher=lambda url, timeout: (_ for _ in ()).throw(RuntimeError('health_failed')),
    )

    ok, image = provider.read()
    assert ok is False
    assert image is None
    health = provider.health()
    assert health['connected'] is False
    assert health['statusReason'] == 'esp32_snapshot_read_failed'


def test_esp32_http_camera_provider_forwards_auth_headers() -> None:
    seen = {}

    def _bytes(url, timeout, headers=None):
        seen['headers'] = dict(headers or {})
        import cv2
        import numpy as np
        ok, encoded = cv2.imencode('.jpg', np.zeros((2, 2, 3), dtype=np.uint8))
        assert ok is True
        return encoded.tobytes()

    def _json(url, timeout, headers=None):
        seen['json_headers'] = dict(headers or {})
        return {'deviceId': 'esp32-cam-01', 'cameraOk': True}

    provider = Esp32HttpCameraProvider(
        base_url='http://device.local',
        auth_header='X-Inspection-Token',
        auth_token='secret-token',
        byte_fetcher=_bytes,
        json_fetcher=_json,
    )

    assert provider.open() is True
    ok, _ = provider.read()
    assert ok is True
    assert seen['headers']['X-Inspection-Token'] == 'secret-token'
    assert seen['json_headers']['X-Inspection-Token'] == 'secret-token'
    health = provider.health()
    assert health['authEnabled'] is True
    assert health['authHeader'] == 'X-Inspection-Token'
