from __future__ import annotations

import shutil
from pathlib import Path

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import BridgeHandshakeCompleteEvent, BridgeHeartbeatEvent, CaptureRequest, CountStats, DecisionPublishedEvent, FaultEvent, FaultRaisedEvent, FsmTransitionEvent, InspectionResult, SortCommand, StationState, VisionFrameAcquiredEvent
except ImportError:  # pragma: no cover - unit-test fallback without generated typed messages
    BridgeHandshakeCompleteEvent = BridgeHeartbeatEvent = CaptureRequest = DecisionPublishedEvent = FaultRaisedEvent = FsmTransitionEvent = VisionFrameAcquiredEvent = None  # type: ignore[assignment]
    from inspection_interfaces.msg import CountStats, FaultEvent, InspectionResult, SortCommand, StationState
from inspection_utils.config_common import ensure_dir
from inspection_utils.runtime_common import ManagedNodeMixin
from inspection_utils.runtime_common import InspectionRuntimeNode
from inspection_utils.runtime_common import qos_profile
from inspection_utils.logging_common import event_to_json, safe_json_loads, utc_now_str
from inspection_utils.transport_common import CAPTURE_REQUEST_TOPIC_TYPED, capture_request_payload_from_message, serialize_payload
from inspection_utils.runtime_event_contracts import BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED, BRIDGE_HEARTBEAT_TOPIC_TYPED, DECISION_PUBLISHED_TOPIC_TYPED, FAULT_RAISED_TOPIC_TYPED, FSM_TRANSITION_TOPIC_TYPED, RuntimeEventDeduper, VISION_FRAME_ACQUIRED_TOPIC_TYPED, is_runtime_event_payload, normalize_runtime_event_message
from inspection_utils.transport_common import normalized_payload_from_typed_message
from inspection_utils.runtime_common import assert_typed_interfaces_available
from inspection_utils.io_common import resolve_resource_path, resolve_runtime_path
from inspection_utils.topic_classification import core_release_topics, topic_classification, topic_classification_catalog
from inspection_utils.config_common import parameter_as_bool
from inspection_utils.station_common import DECISION_OUTPUT_TOPIC, SORT_REQUEST_TOPIC
from .bag_manager import BagManager
from .benchmark_writer import BenchmarkWriter
from .cycle_summary_builder import TraceAccumulator
from .trace_store import TraceStore
from .read_model_writer import ReadModelWriter

from .defaults import DEFAULT_BAG_TOPICS, default_bag_topics


class LoggerNode(ManagedNodeMixin, InspectionRuntimeNode):
    def __init__(self) -> None:
        super().__init__('inspection_logger_node')
        self.declare_parameter('log_root', 'logs/runtime')
        self.declare_parameter('recipe_path', 'config/recipes/default_recipe.yaml')
        self.declare_parameter('station_config_path', 'config/station/station.yaml')
        self.declare_parameter('camera_config_path', 'config/camera/camera.yaml')
        self.declare_parameter('profile_name', 'production')
        self.declare_parameter('profile_config_path', '')
        self.declare_parameter('enable_bag_recording', False)
        self.declare_parameter('bag_topics', default_bag_topics())
        self.declare_parameter('bag_storage_id', 'mcap')
        self.declare_parameter('bag_storage_config_uri', 'config/system/rosbag_mcap_writer.yaml')
        self.root = resolve_runtime_path(str(self.get_parameter('log_root').value), start=__file__)
        ensure_dir(self.root / 'events')
        ensure_dir(self.root / 'results')
        ensure_dir(self.root / 'traces')
        ensure_dir(self.root / 'config_snapshot')
        self.store = TraceStore(self.root)
        self.read_model_writer = ReadModelWriter(self.root)
        self.benchmarks = BenchmarkWriter(self.root)
        self.topic_catalog = topic_classification_catalog()
        self.release_core_topics = core_release_topics()
        self.bag_manager = BagManager()
        self.trace_accumulators: dict[str, TraceAccumulator] = {}
        self.runtime_event_deduper = RuntimeEventDeduper(max_entries=512, ttl_sec=2.0)
        self.create_subscription(String, '/inspection/events', self.on_event, qos_profile('event'))
        self.typed_fsm_transition_sub = self.create_subscription(FsmTransitionEvent, FSM_TRANSITION_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if FsmTransitionEvent is not None else None
        self.typed_vision_frame_sub = self.create_subscription(VisionFrameAcquiredEvent, VISION_FRAME_ACQUIRED_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if VisionFrameAcquiredEvent is not None else None
        self.typed_decision_sub = self.create_subscription(DecisionPublishedEvent, DECISION_PUBLISHED_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if DecisionPublishedEvent is not None else None
        self.typed_bridge_heartbeat_sub = self.create_subscription(BridgeHeartbeatEvent, BRIDGE_HEARTBEAT_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if BridgeHeartbeatEvent is not None else None
        self.typed_bridge_handshake_sub = self.create_subscription(BridgeHandshakeCompleteEvent, BRIDGE_HANDSHAKE_COMPLETE_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if BridgeHandshakeCompleteEvent is not None else None
        self.typed_fault_raised_sub = self.create_subscription(FaultRaisedEvent, FAULT_RAISED_TOPIC_TYPED, self.on_typed_event, qos_profile('event')) if FaultRaisedEvent is not None else None
        self.create_subscription(String, '/inspection/capture_request', self.on_capture_request, qos_profile('control'))
        self.typed_capture_sub = self.create_subscription(CaptureRequest, CAPTURE_REQUEST_TOPIC_TYPED, self.on_typed_capture_request, qos_profile('control')) if CaptureRequest is not None else None
        self.create_subscription(InspectionResult, '/inspection/result', self.on_result, qos_profile('result'))
        self.create_subscription(SortCommand, DECISION_OUTPUT_TOPIC, self.on_decision_output, qos_profile('result'))
        self.create_subscription(SortCommand, SORT_REQUEST_TOPIC, self.on_sort_request, qos_profile('result'))
        self.create_subscription(CountStats, '/station/count_stats', self.on_stats, qos_profile('diagnostics'))
        self.create_subscription(FaultEvent, '/station/fault', self.on_fault, qos_profile('diagnostics'))
        self.create_subscription(StationState, '/station/state', self.on_station, qos_profile('station_state'))
        self.last_station_context: dict[str, str | int] = {'trace_id': '', 'batch_id': '', 'item_id': -1}
        self._snapshot_config()
        self.store.set_run_artifacts(profile_name=str(self.get_parameter('profile_name').value), topic_classification={topic: item.to_dict() for topic, item in self.topic_catalog.items()}, release_core_topics=list(self.release_core_topics))
        self._configure_bag_recording()
        assert_typed_interfaces_available(consumer='inspection_logger_node', symbols={'BridgeHandshakeCompleteEvent': BridgeHandshakeCompleteEvent, 'BridgeHeartbeatEvent': BridgeHeartbeatEvent, 'CaptureRequest': CaptureRequest, 'DecisionPublishedEvent': DecisionPublishedEvent, 'FaultRaisedEvent': FaultRaisedEvent, 'FsmTransitionEvent': FsmTransitionEvent, 'VisionFrameAcquiredEvent': VisionFrameAcquiredEvent})
        self.setup_managed_runtime(node_name='inspection_logger_node')

    def on_configure(self):
        return True, 'logger configured'

    def on_activate(self):
        return True, 'logger active'

    def on_deactivate(self):
        return True, 'logger inactive'

    def on_cleanup(self):
        self._stop_bag_recording('logger_cleanup')
        return True, 'logger cleaned'

    def on_shutdown(self):
        self._stop_bag_recording('logger_shutdown')
        return True, 'logger shutdown'

    def _stop_bag_recording(self, reason: str) -> None:
        try:
            self.bag_manager.stop_recording()
        except Exception as exc:  # pragma: no cover - defensive shutdown path
            self.store.append_event({'time': utc_now_str(), 'type': 'bag_recording_stop_failed', 'reason': reason, 'error': str(exc)})

    def _snapshot_config(self) -> None:
        profile_name = str(self.get_parameter('profile_name').value or 'production').strip() or 'production'
        profile_config_raw = str(self.get_parameter('profile_config_path').value or '').strip()
        snapshot_sources = {
            'recipe.yaml': str(self.get_parameter('recipe_path').value),
            'station.yaml': str(self.get_parameter('station_config_path').value),
            'camera.yaml': str(self.get_parameter('camera_config_path').value),
            'profile.yaml': profile_config_raw or f'config/profiles/{profile_name}.yaml',
        }
        for name, source_path in snapshot_sources.items():
            src = resolve_resource_path(source_path, package_name='inspection_bringup', start=__file__)
            dst = self.root / 'config_snapshot' / name
            try:
                if src.exists():
                    shutil.copy2(src, dst)
            except Exception:
                continue


    def _configure_bag_recording(self) -> None:
        if not parameter_as_bool(self, 'enable_bag_recording', default=False):
            return
        topics = [str(topic) for topic in self.get_parameter('bag_topics').value]
        bag_dir = self.root / 'bags' / utc_now_str().replace(':', '').replace('-', '')
        storage_id = str(self.get_parameter('bag_storage_id').value or 'mcap')
        storage_config_uri = str(self.get_parameter('bag_storage_config_uri').value or '').strip()
        if storage_id != 'mcap':
            storage_config_uri = ''
        self.bag_manager.storage_config_uri = storage_config_uri
        handle = self.bag_manager.start_recording(output_path=bag_dir, topics=topics, storage_id=storage_id, storage_config_uri=storage_config_uri)
        payload = {'time': utc_now_str(), 'type': 'bag_recording_started', 'enabled': handle is not None, 'output_path': str(bag_dir), 'topics': topics, 'storage_id': storage_id, 'storage_config_uri': storage_config_uri, 'command': self.bag_manager.last_command}
        self.store.set_run_artifacts(bag_recording=self.bag_manager.snapshot())
        self.store.append_event(payload)

    def _append_trace(self, trace_id: str, record: dict) -> None:
        self.store.append_trace(trace_id, record)
        self.read_model_writer.record_trace_event(trace_id, dict(record))
        accumulator = self.trace_accumulators.setdefault(trace_id, TraceAccumulator(trace_id=trace_id))
        accumulator.ingest(record)
        if record.get('type') in {'cycle_finish', 'fault'}:
            summary = accumulator.to_summary()
            self.store.append_summary(summary)
            self.read_model_writer.record_summary(
                summary,
                run_artifacts=dict(self.store.run_artifacts),
                config_snapshot={
                    'recipe_path': str(self.root / 'config_snapshot' / 'recipe.yaml'),
                    'station_path': str(self.root / 'config_snapshot' / 'station.yaml'),
                    'camera_path': str(self.root / 'config_snapshot' / 'camera.yaml'),
                    'profile_path': str(self.root / 'config_snapshot' / 'profile.yaml'),
                },
            )
            self.benchmarks.append_summary(summary)

    @staticmethod
    def _layered_record(record: dict, *, event_layer: str, public_type: str = '') -> dict:
        layered = dict(record)
        layered['event_layer'] = str(event_layer or 'normalized')
        if public_type:
            layered['public_type'] = str(public_type)
        return layered


    def _topic_metadata(self, topic: str) -> dict[str, object]:
        """Return release-evidence classification metadata for one topic.

        Args:
            topic: ROS topic name associated with the record or artifact.

        Returns:
            A compact metadata payload with topic class and release-evidence
            eligibility.

        Boundary behavior:
            Unknown topics fail closed to diagnostic/non-release so a new
            diagnostic stream cannot silently become part of formal evidence.
        """
        item = self.topic_catalog.get(topic) or topic_classification(topic)
        return {
            'topic': item.topic,
            'topicClass': item.topic_class,
            'requiredForReleaseEvidence': item.required_for_release_evidence,
            'releaseEvidenceEligible': bool(item.topic_class == 'core' and item.required_for_release_evidence),
            'profile': item.profile,
        }

    def _append_public_projection(self, trace_id: str, source_record: dict, *, public_type: str) -> None:
        projection = self._layered_record(
            {
                'time': source_record.get('time', utc_now_str()),
                'type': 'public_projection',
                'trace_id': trace_id,
                'batch_id': source_record.get('batch_id', ''),
                'item_id': source_record.get('item_id', -1),
                'source_type': source_record.get('type', ''),
                'payload': {key: value for key, value in source_record.items() if key not in {'time', 'event_layer'}},
            },
            event_layer='public_projection',
            public_type=public_type,
        )
        self._append_trace(trace_id, projection)
    def on_event_payload(self, payload: dict[str, object]) -> None:
        if is_runtime_event_payload(payload) and self.runtime_event_deduper.seen_recently(payload):
            return
        record = self._layered_record({'time': utc_now_str(), **payload}, event_layer='raw')
        self.store.append_event(record)
        trace_id = str(record.get('trace_id', ''))
        if trace_id:
            self._append_trace(trace_id, record)

    def on_event(self, msg: String) -> None:
        """Record a generic station event into the append-only runtime stores.

        Args:
            msg: JSON payload transported via ``std_msgs/String``.

        Returns:
            None.

        Raises:
            No intentional exception is swallowed; unexpected failures remain
            visible to the ROS executor.

        Boundary behavior:
            Unknown event shapes are stored as best-effort dictionaries.
        """
        self.on_event_payload(safe_json_loads(msg.data, {'type': 'event', 'message': msg.data}))

    def on_typed_event(self, msg: object) -> None:
        payload = safe_json_loads(getattr(msg, 'payload_json', '') or '{}', {})
        default_event_type = str(payload.get('type', '') or 'runtime_event')
        self.on_event_payload(normalize_runtime_event_message(msg, default_event_type=default_event_type))

    def on_capture_request(self, msg: String) -> None:
        """Persist a legacy capture request event into the trace log.

        Args:
            msg: JSON payload transported via ``std_msgs/String``.

        Returns:
            None.

        Raises:
            No additional exception is raised beyond JSON normalization and store
            append operations.

        Boundary behavior:
            Requests without ``trace_id`` are ignored because they cannot be
            correlated with a runtime trace.
        """
        self.on_capture_request_payload(safe_json_loads(msg.data))

    def on_capture_request_payload(self, record: dict[str, object]) -> None:
        trace_id = str(record.get('trace_id', ''))
        if trace_id:
            normalized = self._layered_record({'time': utc_now_str(), 'type': 'capture_request', **record}, event_layer='normalized')
            self._append_trace(trace_id, normalized)
            self._append_public_projection(trace_id, normalized, public_type='capture.requested')

    def on_typed_capture_request(self, msg) -> None:
        """Convert a typed capture request into the canonical logger path.

        Args:
            msg: Generated ``CaptureRequest`` message or a compatible test double.

        Returns:
            None.

        Raises:
            No additional exception is raised beyond canonical normalization and
            trace append operations.

        Boundary behavior:
            Typed and legacy transports now share one canonical dict payload path
            before persistence.
        """
        self.on_capture_request_payload(normalized_payload_from_typed_message(msg, default_event_type='capture_request', bridge_name='capture_request'))

    def on_result(self, msg: InspectionResult) -> None:
        """Record an inspection result row and enrich the correlated trace bundle.

        Args:
            msg: Structured inspection result published by the vision pipeline.

        Returns:
            None.

        Raises:
            No intentional exception is swallowed; persistence faults remain
            visible to the ROS executor.

        Boundary behavior:
            Trace enrichment is skipped when the detail payload does not contain a
            trace identifier.
        """
        detail = safe_json_loads(msg.detail_json or '{}')
        trace_id = str(detail.get('trace_id', ''))
        row = {
            'time': utc_now_str(),
            'trace_id': trace_id,
            'batch_id': msg.batch_id,
            'item_id': msg.item_id,
            'recipe_id': msg.recipe_id,
            'category': msg.category,
            'defect_type': msg.defect_type,
            'score': msg.score,
            'qr_ok': msg.qr_ok,
            'qr_text': msg.qr_text,
            'orientation_ok': msg.orientation_ok,
            'color_name': msg.color_name,
            'color_ratio': msg.color_ratio,
            'image_path': msg.image_path,
            'annotated_image_path': msg.annotated_image_path,
            'detail_json': msg.detail_json,
        }
        self.store.append_result_row([row['time'], trace_id, msg.batch_id, msg.item_id, msg.recipe_id, msg.category, msg.defect_type, msg.score, msg.qr_ok, msg.qr_text, msg.orientation_ok, msg.color_name, msg.color_ratio, msg.image_path, msg.annotated_image_path, msg.detail_json])
        self.read_model_writer.record_result_row(row)
        if trace_id:
            evidence = detail.get('evidence', {}) if isinstance(detail.get('evidence', {}), dict) else {}
            artifact_writes = evidence.get('artifact_writes', {}) if isinstance(evidence.get('artifact_writes', {}), dict) else {}
            if msg.image_path:
                raw_meta = {'receipt': artifact_writes.get('raw', {}), 'topicEvidence': self._topic_metadata('/inspection/image_raw')}
                self.store.append_artifact_record(trace_id=trace_id, batch_id=msg.batch_id, item_id=msg.item_id, kind='raw', path=str(msg.image_path), meta=raw_meta)
                self.read_model_writer.record_artifact(trace_id=trace_id, batch_id=msg.batch_id, item_id=msg.item_id, kind='raw', path=str(msg.image_path), source='artifact_index', meta=raw_meta)
            if msg.annotated_image_path:
                annotated_meta = {'receipt': artifact_writes.get('annotated', {}), 'topicEvidence': self._topic_metadata('/inspection/image_annotated')}
                self.store.append_artifact_record(trace_id=trace_id, batch_id=msg.batch_id, item_id=msg.item_id, kind='annotated', path=str(msg.annotated_image_path), meta=annotated_meta)
                self.read_model_writer.record_artifact(trace_id=trace_id, batch_id=msg.batch_id, item_id=msg.item_id, kind='annotated', path=str(msg.annotated_image_path), source='artifact_index', meta=annotated_meta)
            normalized = self._layered_record({
                'time': utc_now_str(),
                'type': 'inspection_result',
                'topicEvidence': self._topic_metadata('/inspection/result'),
                'trace_id': trace_id,
                'batch_id': msg.batch_id,
                'item_id': msg.item_id,
                'defect_type': msg.defect_type,
                'score': msg.score,
                'color_name': msg.color_name,
                'qr_ok': msg.qr_ok,
                'orientation_ok': msg.orientation_ok,
                'detail': detail,
            }, event_layer='normalized')
            self._append_trace(trace_id, normalized)
            self._append_public_projection(trace_id, normalized, public_type='inspection.result.finalized')

    def on_decision_output(self, msg: SortCommand) -> None:
        """Append a business decision-output event to the correlated trace.

        Decisions without a correlated ``trace_id`` are ignored because they
        cannot be joined with a runtime trace bundle.
        """
        reason = safe_json_loads(msg.reason or '{}', {'reason': msg.reason})
        trace_id = str(reason.get('trace_id', ''))
        if trace_id:
            normalized = self._layered_record({
                'time': utc_now_str(),
                'type': 'decision_output',
                'trace_id': trace_id,
                'batch_id': msg.batch_id,
                'item_id': msg.item_id,
                'decision': msg.decision,
                'target_bin': msg.target_bin,
                'action_code': msg.action_code,
                'reason': reason,
            }, event_layer='normalized')
            self._append_trace(trace_id, normalized)
            self._append_public_projection(trace_id, normalized, public_type='decision.output.created')

    def on_sort_request(self, msg: SortCommand) -> None:
        """Append a canonical station sort-request event to the trace log.

        Requests without a correlated ``trace_id`` are ignored.
        """
        reason = safe_json_loads(msg.reason or '{}', {'reason': msg.reason})
        trace_id = str(reason.get('trace_id', ''))
        if trace_id:
            normalized = self._layered_record({
                'time': utc_now_str(),
                'type': 'sort_request',
                'trace_id': trace_id,
                'batch_id': msg.batch_id,
                'item_id': msg.item_id,
                'decision': msg.decision,
                'target_bin': msg.target_bin,
                'action_code': msg.action_code,
                'reason': reason,
            }, event_layer='normalized')
            self._append_trace(trace_id, normalized)
            self._append_public_projection(trace_id, normalized, public_type='station.sort.requested')

    def on_stats(self, msg: CountStats) -> None:
        """Persist station counter updates as coarse-grained events."""
        self.store.append_event({'time': utc_now_str(), 'type': 'stats', 'total': msg.total_count, 'ok': msg.ok_count, 'ng': msg.ng_count, 'recheck': msg.recheck_count, 'yield_rate': msg.yield_rate, 'avg_cycle_time_sec': msg.avg_cycle_time_sec})

    def on_fault(self, msg: FaultEvent) -> None:
        """Persist a fault event and attach it to the latest station context."""
        record = self._layered_record({
            'time': utc_now_str(),
            'type': 'fault',
            'trace_id': self.last_station_context.get('trace_id', ''),
            'batch_id': self.last_station_context.get('batch_id', ''),
            'item_id': self.last_station_context.get('item_id', -1),
            'code': msg.fault_code,
            'description': msg.description,
            'recoverable': msg.recoverable,
        }, event_layer='normalized')
        self.store.append_event(record)
        trace_id = str(record.get('trace_id', ''))
        if trace_id:
            self._append_trace(trace_id, record)
            self._append_public_projection(trace_id, record, public_type='station.fault.raised')

    def on_station(self, msg: StationState) -> None:
        """Persist station-state transitions and keep correlation context hot."""
        detail = safe_json_loads(msg.detail)
        trace_id = str(detail.get('trace_id', self.last_station_context.get('trace_id', '')))
        self.last_station_context = {
            'trace_id': trace_id,
            'batch_id': msg.batch_id,
            'item_id': msg.item_id,
        }
        record = self._layered_record({
            'time': utc_now_str(),
            'type': 'station_state',
            'trace_id': trace_id,
            'state': msg.state,
            'item_id': msg.item_id,
            'batch_id': msg.batch_id,
            'detail': detail,
        }, event_layer='normalized')
        self.store.append_event(record)
        if trace_id:
            self._append_trace(trace_id, record)
            self._append_public_projection(trace_id, record, public_type='station.state.updated')


def main() -> None:

    rclpy.init()
    node = LoggerNode()
    try:
        rclpy.spin(node)
    finally:
        node.on_shutdown()
        node.destroy_node()
        rclpy.shutdown()
