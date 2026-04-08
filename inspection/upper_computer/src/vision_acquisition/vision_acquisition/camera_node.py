from __future__ import annotations

import json
import time

import cv2
import numpy as np
import rclpy
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
from std_msgs.msg import String

from inspection_utils.managed_node import ManagedNodeMixin
from inspection_utils.qos import qos_profile
from inspection_utils.param_parsing import parameter_as_bool
from inspection_utils.runtime_node import InspectionRuntimeNode

from .camera_provider import Esp32HttpCameraProvider, MockCameraProvider, OpenCVCameraProvider
from .provider_registry import provider_manifest_catalog


class CameraNode(ManagedNodeMixin, InspectionRuntimeNode):
    """Managed runtime camera publisher.

    The node keeps the public topic contract unchanged while enriching camera
    diagnostics with provider health, publish cadence, and stale-stream status.
    """

    def __init__(self) -> None:
        super().__init__('camera_node')
        self.declare_parameter('camera_provider', 'auto')
        self.declare_parameter('camera_index', 0)
        self.declare_parameter('mock_mode', True)
        self.declare_parameter('mock_color', 'red')
        self.declare_parameter('frame_width', 640)
        self.declare_parameter('frame_height', 480)
        self.declare_parameter('hz', 5.0)
        self.declare_parameter('max_reconnect_attempts', 2)
        self.declare_parameter('reconnect_backoff_sec', 0.05)
        self.declare_parameter('stale_frame_threshold_ms', 1000.0)
        self.declare_parameter('esp32_base_url', 'http://192.168.4.1')
        self.declare_parameter('esp32_snapshot_path', '/api/v1/camera/snapshot')
        self.declare_parameter('esp32_health_path', '/api/v1/camera/health')
        self.declare_parameter('esp32_request_timeout_ms', 1200.0)
        self.declare_parameter('esp32_auth_header', 'X-Inspection-Token')
        self.declare_parameter('esp32_auth_token', '')

        self.bridge = CvBridge()
        self.mock_mode = parameter_as_bool(self, 'mock_mode', default=True)
        self.mock_color = str(self.get_parameter('mock_color').value)
        self.frame_width = int(self.get_parameter('frame_width').value)
        self.frame_height = int(self.get_parameter('frame_height').value)
        self.frame_hz = max(0.1, float(self.get_parameter('hz').value))
        self.camera_provider_name = str(self.get_parameter('camera_provider').value or 'auto').strip().lower()
        self.provider_manifest_catalog = provider_manifest_catalog()
        self.esp32_base_url = str(self.get_parameter('esp32_base_url').value or 'http://192.168.4.1').strip()
        self.esp32_snapshot_path = str(self.get_parameter('esp32_snapshot_path').value or '/api/v1/camera/snapshot').strip()
        self.esp32_health_path = str(self.get_parameter('esp32_health_path').value or '/api/v1/camera/health').strip()
        self.esp32_request_timeout_ms = float(self.get_parameter('esp32_request_timeout_ms').value or 1200.0)
        self.esp32_auth_header = str(self.get_parameter('esp32_auth_header').value or 'X-Inspection-Token').strip()
        self.esp32_auth_token = str(self.get_parameter('esp32_auth_token').value or '').strip()

        if self.mock_mode:
            self.provider = MockCameraProvider(self.make_mock_frame)
        elif self.camera_provider_name == 'esp32_http':
            self.provider = Esp32HttpCameraProvider(
                base_url=self.esp32_base_url,
                snapshot_path=self.esp32_snapshot_path,
                health_path=self.esp32_health_path,
                request_timeout_ms=self.esp32_request_timeout_ms,
                stale_frame_threshold_ms=float(self.get_parameter('stale_frame_threshold_ms').value or 1000.0),
                auth_header=self.esp32_auth_header,
                auth_token=self.esp32_auth_token,
            )
            self.provider.open()
        else:
            self.provider = OpenCVCameraProvider(
                camera_index=int(self.get_parameter('camera_index').value),
                frame_width=self.frame_width,
                frame_height=self.frame_height,
                max_reconnect_attempts=int(self.get_parameter('max_reconnect_attempts').value or 2),
                reconnect_backoff_sec=float(self.get_parameter('reconnect_backoff_sec').value or 0.05),
                stale_frame_threshold_ms=float(self.get_parameter('stale_frame_threshold_ms').value or 1000.0),
            )
            self.provider.open()

        self.image_pub = self.create_publisher(Image, '/inspection/image_raw', qos_profile('sensor_data'))
        self.status_pub = self.create_publisher(String, '/inspection/camera/status', qos_profile('diagnostics'))
        self.timer = self.create_timer(max(0.02, 1.0 / self.frame_hz), self.on_timer)
        self.frame_idx = 0
        self.last_publish_monotonic = 0.0
        self.setup_managed_runtime(node_name='camera_node')

    def on_configure(self) -> tuple[bool, str]:
        return True, 'camera configured'

    def on_activate(self) -> tuple[bool, str]:
        return True, 'camera active'

    def on_deactivate(self) -> tuple[bool, str]:
        return True, 'camera inactive'

    def on_cleanup(self) -> tuple[bool, str]:
        return True, 'camera cleaned'

    def on_shutdown(self) -> tuple[bool, str]:
        self.provider.close()
        return True, 'camera shutdown'

    def make_mock_frame(self) -> np.ndarray:
        frame = np.zeros((self.frame_height, self.frame_width, 3), dtype=np.uint8)
        colors = {
            'red': (0, 0, 255),
            'green': (0, 255, 0),
            'blue': (255, 0, 0),
            'yellow': (0, 255, 255),
        }
        cv2.rectangle(frame, (180, 120), (460, 360), colors.get(self.mock_color, (0, 0, 255)), -1)
        cv2.putText(frame, f'ITEM-{self.frame_idx:04d}', (200, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2)
        cv2.circle(frame, (320, 240), 110, (255, 255, 255), 3)
        return frame

    def _status_payload(self, *, status: str, frame_id: str = '', publish_interval_ms: float = 0.0) -> dict[str, object]:
        health = self.provider.health()
        payload: dict[str, object] = {
            'status': status,
            'frameIndex': int(self.frame_idx),
            'frameId': frame_id,
            'publishIntervalMs': round(float(publish_interval_ms), 3),
            'publishTimestampMonotonic': round(float(self.last_publish_monotonic), 6),
            'expectedIntervalMs': round(1000.0 / self.frame_hz, 3),
            **health,
        }
        status_reason = str(payload.get('statusReason', '')).strip()
        if status == 'camera_read_failed' and not status_reason:
            payload['statusReason'] = 'camera_read_failed'
        return payload

    def on_timer(self) -> None:
        if not self.is_active():
            return

        ok, frame = self.provider.read()
        if not ok or frame is None:
            payload = self._status_payload(status='camera_read_failed')
            self.get_logger().warning(
                'camera read failed reconnects=%s failures=%s reason=%s'
                % (
                    payload.get('reconnectCount', 0),
                    payload.get('readFailures', 0),
                    payload.get('statusReason', ''),
                )
            )
            self._publish_lifecycle_state(
                'camera_read_failed',
                reason='camera_read_failed',
                camera_health=payload,
            )
            status_msg = String()
            status_msg.data = json.dumps(payload, ensure_ascii=False)
            self.status_pub.publish(status_msg)
            return

        publish_now = time.monotonic()
        publish_interval_ms = 0.0
        if self.last_publish_monotonic > 0.0:
            publish_interval_ms = max(0.0, (publish_now - self.last_publish_monotonic) * 1000.0)
        self.last_publish_monotonic = publish_now

        msg = self.bridge.cv2_to_imgmsg(frame, encoding='bgr8')
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = f'frame-{self.frame_idx:06d}'
        self.image_pub.publish(msg)

        payload = self._status_payload(
            status='camera_ok',
            frame_id=msg.header.frame_id,
            publish_interval_ms=publish_interval_ms,
        )
        status_msg = String()
        status_msg.data = json.dumps(payload, ensure_ascii=False)
        self.status_pub.publish(status_msg)
        self._publish_lifecycle_state(
            'camera_frame_published',
            frame_id=msg.header.frame_id,
            frame_index=self.frame_idx,
            camera_health=payload,
        )
        self.frame_idx += 1



def main() -> None:
    rclpy.init()
    node = CameraNode()
    try:
        rclpy.spin(node)
    finally:
        try:
            node.on_shutdown()
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()
