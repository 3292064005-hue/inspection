from __future__ import annotations

import rclpy
from cv_bridge import CvBridge
from sensor_msgs.msg import Image
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import CaptureRequest, InspectionResult, VisionFrameAcquiredEvent
except ImportError:  # pragma: no cover - unit-test fallback without generated typed messages
    CaptureRequest = VisionFrameAcquiredEvent = None  # type: ignore[assignment]
    from inspection_interfaces.msg import InspectionResult
from inspection_utils.config_common import build_effective_runtime_bundle, ensure_dir
from inspection_utils.runtime_common import ManagedNodeMixin
from inspection_utils.runtime_common import InspectionRuntimeNode
from inspection_utils.runtime_common import qos_profile
from inspection_utils.io_common import resolve_resource_path, resolve_runtime_path
from inspection_utils.config_common import parameter_as_bool
from inspection_utils.logging_common import safe_json_loads
from inspection_utils.transport_common import CAPTURE_REQUEST_TOPIC_TYPED, capture_request_payload_from_message, serialize_payload
from inspection_utils.runtime_event_contracts import VISION_FRAME_ACQUIRED_TOPIC_TYPED, populate_vision_frame_acquired_message, publish_dual_runtime_event
from inspection_utils.transport_common import normalized_payload_from_typed_message
from inspection_utils.runtime_common import assert_typed_interfaces_available
from .artifact_writer import ArtifactWriter
from .detectors import compile_pipeline, detector_manifest_catalog
from .frame_binding import FrameBindingBuffer
from .performance import VisionLatencyBudget
from .processor_runtime import ProcessorArtifactRuntime, ProcessorExecutionRuntime


class VisionProcessorNode(ManagedNodeMixin, InspectionRuntimeNode):
    def __init__(self) -> None:
        super().__init__('vision_processor_node')
        self.declare_parameter('recipe_path', 'config/recipes/default_recipe.yaml')
        self.declare_parameter('output_dir', 'logs/runtime')
        self.declare_parameter('camera_config_path', 'config/camera/camera.yaml')
        self.declare_parameter('profile_name', 'production')
        self.declare_parameter('batch_id', 'BATCH_DEMO')
        self.declare_parameter('compatibility_path', 'config/compatibility/matrix.yaml')
        self.declare_parameter('profile_config_path', '')
        self.declare_parameter('process_every_frame_without_trigger', False)
        self.declare_parameter('capture_fallback_window_ms', 250.0)
        self.declare_parameter('artifact_writer_enabled', True)
        self.declare_parameter('artifact_writer_queue_size', 32)
        self.declare_parameter('artifact_writer_flush_timeout_sec', 5.0)
        self.declare_parameter('artifact_backpressure_threshold', 0.8)
        self.declare_parameter('artifact_overload_policy', 'drop_annotated')
        self.declare_parameter('artifact_overload_flush_timeout_ms', 10.0)
        self.declare_parameter('capture_pending_queue_size', 32)
        self.declare_parameter('capture_pending_overload_policy', 'drop_oldest')
        self.declare_parameter('latency_budget_bind_wait_ms', 80.0)
        self.declare_parameter('latency_budget_analyze_ms', 120.0)
        self.declare_parameter('latency_budget_artifact_persist_ms', 40.0)
        self.declare_parameter('latency_budget_publish_ms', 20.0)
        self.declare_parameter('latency_budget_total_ms', 200.0)
        self.recipe_path = str(resolve_resource_path(str(self.get_parameter('recipe_path').value), package_name='inspection_bringup', start=__file__))
        camera_config_path = str(resolve_resource_path(str(self.get_parameter('camera_config_path').value), package_name='inspection_bringup', start=__file__))
        profile_name = str(self.get_parameter('profile_name').value)
        compatibility_path = str(resolve_resource_path(str(self.get_parameter('compatibility_path').value), package_name='inspection_bringup', start=__file__))
        profile_config_raw = str(self.get_parameter('profile_config_path').value or '').strip()
        profile_config_path = str(resolve_resource_path(profile_config_raw, package_name='inspection_bringup', start=__file__)) if profile_config_raw else None
        effective_bundle = build_effective_runtime_bundle(recipe_path=self.recipe_path, camera_config_path=camera_config_path, profile_name=profile_name, profile_config_path=profile_config_path, compatibility_path=compatibility_path, resource_package_name='inspection_bringup', resource_start=__file__)
        self.profile_bundle = effective_bundle['profile_bundle']
        self.compatibility_bundle = effective_bundle['compatibility_bundle']
        self.recipe = effective_bundle['recipe']
        self.output_dir = resolve_runtime_path(str(self.get_parameter('output_dir').value), start=__file__)
        ensure_dir(self.output_dir / 'images' / 'raw')
        ensure_dir(self.output_dir / 'images' / 'annotated')
        self.default_batch_id = str(self.get_parameter('batch_id').value)
        self.process_without_trigger = parameter_as_bool(self, 'process_every_frame_without_trigger', default=False)
        self.capture_fallback_window_sec = float(self.get_parameter('capture_fallback_window_ms').value) / 1000.0
        self.capture_pending_queue_size = max(1, int(self.get_parameter('capture_pending_queue_size').value))
        self.capture_pending_overload_policy = str(self.get_parameter('capture_pending_overload_policy').value or 'drop_oldest').strip().lower() or 'drop_oldest'
        self.artifact_writer_enabled = parameter_as_bool(self, 'artifact_writer_enabled', default=False)
        self.artifact_writer_flush_timeout_sec = float(self.get_parameter('artifact_writer_flush_timeout_sec').value)
        self.artifact_backpressure_threshold = max(0.05, min(1.0, float(self.get_parameter('artifact_backpressure_threshold').value)))
        self.artifact_overload_policy = str(self.get_parameter('artifact_overload_policy').value or 'drop_annotated').strip().lower() or 'drop_annotated'
        self.artifact_overload_flush_timeout_sec = max(0.0, float(self.get_parameter('artifact_overload_flush_timeout_ms').value) / 1000.0)
        self.bridge = CvBridge()
        self.frame_buffer = FrameBindingBuffer(fallback_window_sec=self.capture_fallback_window_sec, max_pending_requests=self.capture_pending_queue_size, pending_overload_policy=self.capture_pending_overload_policy)
        self.detector_manifest_catalog = detector_manifest_catalog()
        self.pipeline = compile_pipeline(self.recipe)
        self.artifact_writer = ArtifactWriter(
            max_queue_size=int(self.get_parameter('artifact_writer_queue_size').value),
            overload_threshold=self.artifact_backpressure_threshold,
        ) if self.artifact_writer_enabled else None
        self.latency_budget = VisionLatencyBudget(
            bind_wait_ms=float(self.get_parameter('latency_budget_bind_wait_ms').value),
            analyze_ms=float(self.get_parameter('latency_budget_analyze_ms').value),
            artifact_persist_ms=float(self.get_parameter('latency_budget_artifact_persist_ms').value),
            publish_ms=float(self.get_parameter('latency_budget_publish_ms').value),
            total_ms=float(self.get_parameter('latency_budget_total_ms').value),
        )
        self.frame_index = 0
        self.result_pub = self.create_publisher(InspectionResult, '/inspection/result', qos_profile('result'))
        self.annotated_pub = self.create_publisher(Image, '/inspection/image_annotated', qos_profile('sensor_data'))
        self.debug_pub = self.create_publisher(String, '/inspection/result_raw', qos_profile('event'))
        self.sub = self.create_subscription(Image, '/inspection/image_raw', self.on_image, qos_profile('sensor_data'))
        self.capture_sub = self.create_subscription(String, '/inspection/capture_request', self.on_capture_request, qos_profile('control'))
        self.typed_capture_sub = self.create_subscription(CaptureRequest, CAPTURE_REQUEST_TOPIC_TYPED, self.on_typed_capture_request, qos_profile('control')) if CaptureRequest is not None else None
        self.event_pub = self.create_publisher(String, '/inspection/events', qos_profile('event'))
        self.typed_vision_frame_event_pub = self.create_publisher(VisionFrameAcquiredEvent, VISION_FRAME_ACQUIRED_TOPIC_TYPED, qos_profile('event')) if VisionFrameAcquiredEvent is not None else None
        self.fallback_item_id = 0
        self.last_trace_id = ''
        self.last_trace_started_at = 0.0
        self.artifact_runtime = ProcessorArtifactRuntime(self)
        self.execution_runtime = ProcessorExecutionRuntime(self, self.artifact_runtime)
        assert_typed_interfaces_available(consumer='vision_processor_node', symbols={'CaptureRequest': CaptureRequest, 'VisionFrameAcquiredEvent': VisionFrameAcquiredEvent})
        self.setup_managed_runtime(node_name='vision_processor_node')

    def _emit_event(self, event_type: str, **fields) -> None:
        payload_json = event_to_json(event_type, node='vision_processor_node', **fields)
        if event_type == 'vision_frame_acquired':
            publish_dual_runtime_event(
                event_type='vision_frame_acquired',
                legacy_publisher=self.event_pub,
                typed_publisher=self.typed_vision_frame_event_pub,
                typed_message_cls=VisionFrameAcquiredEvent,
                populate_message=populate_vision_frame_acquired_message,
                payload=safe_json_loads(payload_json),
            )
            return
        evt = String()
        evt.data = payload_json
        self.event_pub.publish(evt)

    def on_configure(self):
        self.pipeline = compile_pipeline(self.recipe)
        if self.artifact_writer_enabled and self.artifact_writer is None:
            self.artifact_writer = ArtifactWriter(
                max_queue_size=int(self.get_parameter('artifact_writer_queue_size').value),
                overload_threshold=self.artifact_backpressure_threshold,
            )
        self.latency_budget = VisionLatencyBudget(
            bind_wait_ms=float(self.get_parameter('latency_budget_bind_wait_ms').value),
            analyze_ms=float(self.get_parameter('latency_budget_analyze_ms').value),
            artifact_persist_ms=float(self.get_parameter('latency_budget_artifact_persist_ms').value),
            publish_ms=float(self.get_parameter('latency_budget_publish_ms').value),
            total_ms=float(self.get_parameter('latency_budget_total_ms').value),
        )
        return True, 'vision processor configured'

    def on_activate(self):
        return True, 'vision processor active'

    def on_deactivate(self):
        return True, 'vision processor inactive'

    def on_cleanup(self):
        self._close_artifact_writer()
        return True, 'vision processor cleaned'

    def on_shutdown(self):
        self._close_artifact_writer()
        return True, 'vision processor shutdown'
    def on_image(self, msg: Image) -> None:
        """Process an incoming raw camera frame.

        Args:
            msg: ROS image message received from the acquisition node.

        Returns:
            None.

        Raises:
            Any exception raised by the execution runtime is allowed to bubble to
            the ROS executor so the station can surface the fault explicitly.

        Boundary behavior:
            Frames received while the node is inactive are discarded by the
            runtime helper.
        """
        self.execution_runtime.handle_image(msg)

    def on_capture_request(self, msg: String) -> None:
        """Handle a legacy string-encoded capture request.

        Args:
            msg: JSON payload transported via ``std_msgs/String``.

        Returns:
            None.

        Raises:
            Any exception raised by the execution runtime.

        Boundary behavior:
            Malformed payloads are normalized inside the execution runtime.
        """
        self.handle_capture_request_payload(safe_json_loads(msg.data))

    def handle_capture_request_payload(self, payload: dict[str, object]) -> None:
        """Forward one canonical capture request into the execution runtime.

        Args:
            payload: Canonical capture-request payload decoded from either the
                legacy JSON topic or the typed message boundary.

        Returns:
            None. The request is either ignored when inactive or forwarded to
            the runtime for immediate queueing/processing.

        Raises:
            No exception is intentionally raised from this boundary method.

        Boundary behavior:
            Inactive lifecycle states emit an audit event and drop the request
            instead of rebuilding any legacy bridge payloads.
        """
        if not str(payload.get('batch_id', '')).strip():
            payload = dict(payload)
            payload['batch_id'] = self.default_batch_id
        self.execution_runtime.handle_capture_request_payload(dict(payload))

    def on_typed_capture_request(self, msg) -> None:
        """Normalize a typed capture request into the canonical processing path.

        Args:
            msg: Generated ``CaptureRequest`` message or a compatible test double.

        Returns:
            None.

        Raises:
            Any exception raised by the execution runtime.

        Boundary behavior:
            Typed and legacy transports now converge on one canonical dict payload
            before the execution runtime sees the request.
        """
        self.handle_capture_request_payload(normalized_payload_from_typed_message(msg, default_event_type='capture_request', bridge_name='capture_request'))

    def _build_output_name(self, item_id: int, trace_id: str) -> str:
        """Build the canonical artifact file stem for a processed frame.

        Args:
            item_id: Station item identifier.
            trace_id: Runtime trace identifier.

        Returns:
            Canonical artifact file stem.

        Raises:
            No additional exception is raised beyond the delegated runtime helper.

        Boundary behavior:
            Empty trace identifiers fall back to the runtime helper's naming rule.
        """
        return self.artifact_runtime.build_output_name(item_id, trace_id)

    def _close_artifact_writer(self) -> None:
        """Flush and close the asynchronous artifact writer if one is active.

        Args:
            None.

        Returns:
            None.

        Raises:
            No additional exception is raised beyond the delegated runtime helper.

        Boundary behavior:
            Repeated calls are safe and behave as no-ops once the writer is closed.
        """
        self.artifact_runtime.close_artifact_writer()

    def _empty_writer_snapshot(self) -> dict[str, object]:
        """Return an empty artifact-writer status snapshot.

        Args:
            None.

        Returns:
            Default writer snapshot used when no background writer is configured.

        Raises:
            No additional exception is raised beyond the delegated runtime helper.

        Boundary behavior:
            The snapshot is always JSON-serializable.
        """
        return self.artifact_runtime.empty_writer_snapshot()

    def _persist_artifact(self, path, image, *, kind: str, trace_id: str, item_id: int, batch_id: str):
        """Persist a raw or annotated artifact through the runtime abstraction.

        Args:
            path: Destination artifact path.
            image: Image matrix to persist.
            kind: Artifact category such as ``raw`` or ``annotated``.
            trace_id: Runtime trace identifier.
            item_id: Station item identifier.
            batch_id: Active batch identifier.

        Returns:
            Persistence receipt produced by ``ProcessorArtifactRuntime``.

        Raises:
            Any exception raised by the runtime persistence layer.

        Boundary behavior:
            The runtime may downgrade or drop writes according to the configured
            backpressure policy.
        """
        return self.artifact_runtime.persist_artifact(path, image, kind=kind, trace_id=trace_id, item_id=item_id, batch_id=batch_id)

    def _process_bound(self, request: dict, frame) -> None:
        """Process a frame bound to a capture request.

        Args:
            request: Normalized capture request payload.
            frame: Bound frame payload from the frame buffer.

        Returns:
            None.

        Raises:
            Any exception raised by the execution runtime.

        Boundary behavior:
            Request/frame mismatches are handled inside the runtime helper.
        """
        self.execution_runtime.process_bound(request, frame)


def main() -> None:

    rclpy.init()
    node = VisionProcessorNode()
    try:
        rclpy.spin(node)
    finally:
        node.on_shutdown()
        node.destroy_node()
        rclpy.shutdown()
