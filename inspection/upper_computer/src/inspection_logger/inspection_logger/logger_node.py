from __future__ import annotations

import shutil
from pathlib import Path

import rclpy
from std_msgs.msg import String

try:
    from inspection_interfaces.msg import CaptureRequest, CountStats, FaultEvent, InspectionResult, SortCommand, StationState
except ImportError:  # pragma: no cover - unit-test fallback without generated typed messages
    CaptureRequest = None  # type: ignore[assignment]
    from inspection_interfaces.msg import CountStats, FaultEvent, InspectionResult, SortCommand, StationState
from inspection_utils.config import ensure_dir
from inspection_utils.managed_node import ManagedNodeMixin
from inspection_utils.runtime_node import InspectionRuntimeNode
from inspection_utils.qos import qos_profile
from inspection_utils.logging_tools import event_to_json, safe_json_loads, utc_now_str
from inspection_utils.transport_contracts import CAPTURE_REQUEST_TOPIC_TYPED, capture_request_payload_from_message, serialize_payload
from inspection_utils.transport_adapters import legacy_payload_json_from_typed_message
from inspection_utils.typed_interfaces import assert_typed_interfaces_available
from inspection_utils.paths import resolve_resource_path, resolve_runtime_path
from inspection_utils.param_parsing import parameter_as_bool
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
        self.bag_manager = BagManager()
        self.trace_accumulators: dict[str, TraceAccumulator] = {}
        self.create_subscription(String, '/inspection/events', self.on_event, qos_profile('event'))
        self.create_subscription(String, '/inspection/capture_request', self.on_capture_request, qos_profile('control'))
        self.typed_capture_sub = self.create_subscription(CaptureRequest, CAPTURE_REQUEST_TOPIC_TYPED, self.on_typed_capture_request, qos_profile('control')) if CaptureRequest is not None else None
        self.create_subscription(InspectionResult, '/inspection/result', self.on_result, qos_profile('result'))
        self.create_subscription(SortCommand, '/station/sort_cmd', self.on_sort_cmd, qos_profile('result'))
        self.create_subscription(CountStats, '/station/count_stats', self.on_stats, qos_profile('diagnostics'))
        self.create_subscription(FaultEvent, '/station/fault', self.on_fault, qos_profile('diagnostics'))
        self.create_subscription(StationState, '/station/state', self.on_station, qos_profile('station_state'))
        self.last_station_context: dict[str, str | int] = {'trace_id': '', 'batch_id': '', 'item_id': -1}
        self._snapshot_config()
        self.store.set_run_artifacts(profile_name=str(self.get_parameter('profile_name').value))
        self._configure_bag_recording()
        assert_typed_interfaces_available(consumer='inspection_logger_node', symbols={'CaptureRequest': CaptureRequest})
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
        record = safe_json_loads(msg.data, {'type': 'event', 'message': msg.data})
        record = {'time': utc_now_str(), **record}
        self.store.append_event(record)
        trace_id = str(record.get('trace_id', ''))
        if trace_id:
            self._append_trace(trace_id, record)

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
        record = safe_json_loads(msg.data)
        trace_id = str(record.get('trace_id', ''))
        if trace_id:
            self._append_trace(trace_id, {'time': utc_now_str(), 'type': 'capture_request', **record})

    def on_typed_capture_request(self, msg) -> None:
        """Convert a typed capture request to the legacy logger path.

        Args:
            msg: Generated ``CaptureRequest`` message or a compatible test double.

        Returns:
            None.

        Raises:
            No additional exception is raised beyond the delegated legacy handler.

        Boundary behavior:
            When ``payload_json`` is absent, the method synthesizes a compatible
            JSON payload from the typed message fields.
        """
        legacy = String()
        legacy.data = legacy_payload_json_from_typed_message(msg, default_event_type='capture_request')
        self.on_capture_request(legacy)

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
                self.store.append_artifact_record(trace_id=trace_id, batch_id=msg.batch_id, item_id=msg.item_id, kind='raw', path=str(msg.image_path), meta={'receipt': artifact_writes.get('raw', {})})
                self.read_model_writer.record_artifact(trace_id=trace_id, batch_id=msg.batch_id, item_id=msg.item_id, kind='raw', path=str(msg.image_path), source='artifact_index', meta={'receipt': artifact_writes.get('raw', {})})
            if msg.annotated_image_path:
                self.store.append_artifact_record(trace_id=trace_id, batch_id=msg.batch_id, item_id=msg.item_id, kind='annotated', path=str(msg.annotated_image_path), meta={'receipt': artifact_writes.get('annotated', {})})
                self.read_model_writer.record_artifact(trace_id=trace_id, batch_id=msg.batch_id, item_id=msg.item_id, kind='annotated', path=str(msg.annotated_image_path), source='artifact_index', meta={'receipt': artifact_writes.get('annotated', {})})
            self._append_trace(trace_id, {
                'time': utc_now_str(),
                'type': 'inspection_result',
                'trace_id': trace_id,
                'batch_id': msg.batch_id,
                'item_id': msg.item_id,
                'defect_type': msg.defect_type,
                'score': msg.score,
                'color_name': msg.color_name,
                'qr_ok': msg.qr_ok,
                'orientation_ok': msg.orientation_ok,
                'detail': detail,
            })

    def on_sort_cmd(self, msg: SortCommand) -> None:
        """Append a sorter command event to the correlated trace.

        Args:
            msg: Structured sort command emitted by the decision node.

        Returns:
            None.

        Raises:
            No additional exception is raised beyond store append operations.

        Boundary behavior:
            Commands without a correlated ``trace_id`` are ignored.
        """
        reason = safe_json_loads(msg.reason or '{}', {'reason': msg.reason})
        trace_id = str(reason.get('trace_id', ''))
        if trace_id:
            self._append_trace(trace_id, {
                'time': utc_now_str(),
                'type': 'sort_command',
                'trace_id': trace_id,
                'batch_id': msg.batch_id,
                'item_id': msg.item_id,
                'decision': msg.decision,
                'target_bin': msg.target_bin,
                'action_code': msg.action_code,
                'reason': reason,
            })

    def on_stats(self, msg: CountStats) -> None:
        """Persist station counter updates as coarse-grained events."""
        self.store.append_event({'time': utc_now_str(), 'type': 'stats', 'total': msg.total_count, 'ok': msg.ok_count, 'ng': msg.ng_count, 'recheck': msg.recheck_count, 'yield_rate': msg.yield_rate, 'avg_cycle_time_sec': msg.avg_cycle_time_sec})

    def on_fault(self, msg: FaultEvent) -> None:
        """Persist a fault event and attach it to the latest station context."""
        record = {
            'time': utc_now_str(),
            'type': 'fault',
            'trace_id': self.last_station_context.get('trace_id', ''),
            'batch_id': self.last_station_context.get('batch_id', ''),
            'item_id': self.last_station_context.get('item_id', -1),
            'code': msg.fault_code,
            'description': msg.description,
            'recoverable': msg.recoverable,
        }
        self.store.append_event(record)
        trace_id = str(record.get('trace_id', ''))
        if trace_id:
            self._append_trace(trace_id, record)

    def on_station(self, msg: StationState) -> None:
        """Persist station-state transitions and keep correlation context hot."""
        detail = safe_json_loads(msg.detail)
        trace_id = str(detail.get('trace_id', self.last_station_context.get('trace_id', '')))
        self.last_station_context = {
            'trace_id': trace_id,
            'batch_id': msg.batch_id,
            'item_id': msg.item_id,
        }
        record = {
            'time': utc_now_str(),
            'type': 'station_state',
            'trace_id': trace_id,
            'state': msg.state,
            'item_id': msg.item_id,
            'batch_id': msg.batch_id,
            'detail': detail,
        }
        self.store.append_event(record)
        if trace_id:
            self._append_trace(trace_id, record)


def main() -> None:

    rclpy.init()
    node = LoggerNode()
    try:
        rclpy.spin(node)
    finally:
        node.on_shutdown()
        node.destroy_node()
        rclpy.shutdown()
