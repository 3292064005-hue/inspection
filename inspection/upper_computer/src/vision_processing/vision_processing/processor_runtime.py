from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from typing import TYPE_CHECKING

try:
    from std_msgs.msg import String
except ImportError:  # pragma: no cover - unit-test fallback without ROS message generation
    class String:  # type: ignore[override]
        def __init__(self) -> None:
            self.data = ''


if TYPE_CHECKING:  # pragma: no cover
    from sensor_msgs.msg import Image
    from inspection_interfaces.msg import InspectionResult
from inspection_utils.image_tools import save_image
from inspection_utils.logging_tools import event_to_json, safe_json_loads
from inspection_utils.paths import sanitize_trace_id

from .artifact_writer import ArtifactWriteReceipt
from .detectors import process_frame
from .frame_binding import FrameSample


class ProcessorArtifactRuntime:
    """Handle artifact writer lifecycle and persistence fallbacks for the vision node."""

    def __init__(self, node: Any) -> None:
        self.node = node

    def build_output_name(self, item_id: int, trace_id: str) -> str:
        safe_trace = sanitize_trace_id(trace_id, item_id=item_id)
        return f'{item_id:05d}_{safe_trace}'

    def close_artifact_writer(self) -> tuple[bool, str]:
        writer = getattr(self.node, 'artifact_writer', None)
        if writer is None:
            return True, ''
        try:
            writer.close(timeout_sec=self.node.artifact_writer_flush_timeout_sec)
            self.node.artifact_writer = None
            return True, ''
        except Exception as exc:  # pragma: no cover - defensive cleanup path
            self.node.artifact_writer = None
            self.node._emit_event('artifact_writer_close_failed', error=str(exc))
            return False, str(exc)

    def empty_writer_snapshot(self) -> dict[str, object]:
        return {
            'pending': 0,
            'written': 0,
            'failed': 0,
            'sync_fallback': 0,
            'droppedOverload': 0,
            'last_error': '',
            'closed': True,
            'queue_capacity': 0,
            'queueUsage': 0.0,
            'highWatermark': 0,
            'maxQueueUsage': 0.0,
            'flushTimeouts': 0,
            'queueRejected': 0,
            'lastFlushDurationMs': 0.0,
            'overloaded': False,
            'overloadThreshold': round(self.node.artifact_backpressure_threshold, 4),
        }

    def persist_artifact(self, path: Path, image: Any, *, kind: str, trace_id: str, item_id: int, batch_id: str) -> ArtifactWriteReceipt:
        writer = getattr(self.node, 'artifact_writer', None)
        if writer is None:
            saved_path = save_image(path, image)
            return ArtifactWriteReceipt(path=saved_path, status='sync_fallback', queue_depth=0, queue_usage=0.0, submitted_at_monotonic=time.monotonic())
        if writer.is_overloaded() and kind == 'annotated' and self.node.artifact_overload_policy == 'drop_annotated':
            return writer.drop_overload(path)
        if writer.is_overloaded() and self.node.artifact_overload_policy == 'flush_then_queue' and self.node.artifact_overload_flush_timeout_sec > 0.0:
            writer.flush(timeout_sec=self.node.artifact_overload_flush_timeout_sec)
        receipt = writer.submit(path, image, kind=kind, trace_id=trace_id, item_id=item_id, batch_id=batch_id)
        if receipt.status == 'queue_overload' and kind == 'annotated' and self.node.artifact_overload_policy == 'drop_annotated':
            return writer.drop_overload(path)
        if receipt.status == 'queue_overload' and kind == 'raw' and self.node.artifact_overload_flush_timeout_sec > 0.0:
            writer.flush(timeout_sec=self.node.artifact_overload_flush_timeout_sec)
            retry = writer.submit(path, image, kind=kind, trace_id=trace_id, item_id=item_id, batch_id=batch_id)
            if retry.status != 'queue_overload':
                return retry
        return receipt


class ProcessorExecutionRuntime:
    """Encapsulate frame binding, dedup, inference, artifact persistence, and publication."""

    def __init__(self, node: Any, artifacts: ProcessorArtifactRuntime) -> None:
        self.node = node
        self.artifacts = artifacts

    def handle_image(self, msg) -> None:
        if not self.node.is_active():
            return
        frame = self.node.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        bound = FrameSample(frame_index=self.node.frame_index, monotonic_ts=time.monotonic(), stamp=msg.header.stamp, header=msg.header, image=frame)
        self.node.frame_index += 1
        for request, sample in self.node.frame_buffer.push_frame(bound):
            self.process_bound(request, sample)
        if self.node.process_without_trigger:
            request = {
                'item_id': self.node.fallback_item_id,
                'batch_id': self.node.default_batch_id,
                'trace_id': f'AUTO-{self.node.fallback_item_id:05d}',
                'frame_index': bound.frame_index,
                '_request_monotonic_ts': time.monotonic(),
            }
            self.process_bound(request, bound)
            self.node.fallback_item_id += 1

    def handle_capture_request(self, msg: String) -> None:
        if self.node.lifecycle_state == 'FINALIZED':
            return
        request = safe_json_loads(
            msg.data,
            {'item_id': self.node.fallback_item_id, 'batch_id': self.node.default_batch_id, 'trace_id': f'FALLBACK-{self.node.fallback_item_id:05d}'},
        )
        request['_request_monotonic_ts'] = time.monotonic()
        if request.get('trace_id') == self.node.last_trace_id and (time.monotonic() - self.node.last_trace_started_at) < 0.2:
            self.node._emit_event('vision_capture_deduplicated', trace_id=request.get('trace_id', ''), item_id=int(request.get('item_id', -1)))
            return
        bound = self.node.frame_buffer.submit_request(request, monotonic_ts=float(request['_request_monotonic_ts']))
        if bound is not None:
            self.process_bound(request, bound)
            return
        pending_status = getattr(self.node.frame_buffer, 'last_submit_status', 'queued')
        self.node._emit_event(
            'vision_capture_pending',
            trace_id=request.get('trace_id', ''),
            item_id=int(request.get('item_id', -1)),
            pending_status=pending_status,
            pending_depth=len(self.node.frame_buffer.pending),
            pending_capacity=self.node.capture_pending_queue_size,
        )
        if pending_status in {'drop_oldest', 'drop_newest'}:
            self.node._emit_event(
                'vision_capture_pending_overflow',
                trace_id=request.get('trace_id', ''),
                item_id=int(request.get('item_id', -1)),
                pending_status=pending_status,
                pending_depth=len(self.node.frame_buffer.pending),
                pending_capacity=self.node.capture_pending_queue_size,
                pending_policy=self.node.capture_pending_overload_policy,
            )

    def process_bound(self, request: dict[str, Any], frame: FrameSample) -> None:
        item_id = int(request.get('item_id', self.node.fallback_item_id))
        batch_id = str(request.get('batch_id', self.node.default_batch_id))
        trace_id = str(request.get('trace_id', f'TRACE-{item_id:05d}'))
        request_monotonic = float(request.get('_request_monotonic_ts', time.monotonic()) or time.monotonic())
        self.node.last_trace_id = trace_id
        self.node.last_trace_started_at = time.monotonic()
        image = frame.image.copy()
        self.node._emit_event(
            'vision_frame_acquired',
            item_id=item_id,
            batch_id=batch_id,
            trace_id=trace_id,
            frame_index=frame.frame_index,
            lifecycle_state=self.node.lifecycle_state,
            pipeline=self.node.pipeline.to_dict(),
        )
        total_started = time.monotonic()
        bind_wait_ms = max(0.0, (total_started - request_monotonic) * 1000.0)
        frame_age_ms = max(0.0, (total_started - frame.monotonic_ts) * 1000.0)

        analyze_started = time.monotonic()
        summary, vis = process_frame(image, self.node.recipe, item_id=item_id, batch_id=batch_id, trace_id=trace_id, pipeline=self.node.pipeline, copy_input=False)
        analyze_ms = (time.monotonic() - analyze_started) * 1000.0
        summary.processing_ms = round(analyze_ms, 3)

        file_stem = self.artifacts.build_output_name(item_id, trace_id)
        raw_path = str(self.node.output_dir / 'images' / 'raw' / f'{file_stem}.png')
        anno_path = str(self.node.output_dir / 'images' / 'annotated' / f'{file_stem}.png')

        persist_started = time.monotonic()
        raw_receipt = self.artifacts.persist_artifact(Path(raw_path), image, kind='raw', trace_id=trace_id, item_id=item_id, batch_id=batch_id)
        anno_receipt = self.artifacts.persist_artifact(Path(anno_path), vis, kind='annotated', trace_id=trace_id, item_id=item_id, batch_id=batch_id)
        artifact_persist_ms = (time.monotonic() - persist_started) * 1000.0

        summary.evidence['raw_path'] = raw_path if raw_receipt.status != 'queue_overload' else ''
        summary.evidence['annotated_path'] = anno_path if anno_receipt.status not in {'dropped_overload', 'queue_overload'} else ''
        summary.evidence['frame_index'] = frame.frame_index
        summary.evidence['pipeline'] = self.node.pipeline.to_dict()
        summary.evidence['artifact_writes'] = {'raw': raw_receipt.to_dict(), 'annotated': anno_receipt.to_dict()}
        summary.evidence['backpressurePolicy'] = self.node.artifact_overload_policy

        publish_started = time.monotonic()
        from inspection_interfaces.msg import InspectionResult
        result = InspectionResult()
        result.stamp = frame.stamp if frame.stamp is not None else self.node.get_clock().now().to_msg()
        result.batch_id = batch_id
        result.item_id = item_id
        result.recipe_id = self.node.recipe.get('recipe_id', 'default_recipe')
        result.valid = summary.valid
        result.category = summary.category
        result.defect_type = summary.defect_type
        result.score = float(summary.score)
        result.qr_text = summary.qr_text
        result.qr_ok = summary.qr_ok
        result.orientation_ok = summary.orientation_ok
        result.color_name = summary.color_name
        result.color_ratio = float(summary.color_ratio)
        result.image_path = raw_path if raw_receipt.status != 'queue_overload' else ''
        result.annotated_image_path = anno_path if anno_receipt.status not in {'dropped_overload', 'queue_overload'} else ''
        result.detail_json = summary.to_detail_json()
        self.node.result_pub.publish(result)
        anno_msg = self.node.bridge.cv2_to_imgmsg(vis, encoding='bgr8')
        anno_msg.header = frame.header if frame.header is not None else anno_msg.header
        self.node.annotated_pub.publish(anno_msg)
        debug = String()
        debug.data = event_to_json('vision_result_raw', item_id=item_id, trace_id=trace_id, batch_id=batch_id, metrics=summary.metrics, warnings=summary.warnings, evidence=summary.evidence, processing_ms=summary.processing_ms)
        self.node.debug_pub.publish(debug)
        publish_ms = (time.monotonic() - publish_started) * 1000.0

        artifact_writer_snapshot = self.node.artifact_writer.snapshot() if self.node.artifact_writer is not None else self.artifacts.empty_writer_snapshot()
        stage_timings_ms = {
            'bindWaitMs': round(bind_wait_ms, 3),
            'frameAgeMs': round(frame_age_ms, 3),
            'analyzeMs': round(analyze_ms, 3),
            'artifactPersistMs': round(artifact_persist_ms, 3),
            'publishMs': round(publish_ms, 3),
            'totalMs': round((time.monotonic() - total_started) * 1000.0, 3),
        }
        latency_budget = self.node.latency_budget.evaluate(stage_timings_ms)
        self.node._emit_event(
            'vision_capture_done',
            item_id=item_id,
            batch_id=batch_id,
            trace_id=trace_id,
            frame_index=frame.frame_index,
            processing_ms=summary.processing_ms,
            result_valid=summary.valid,
            warnings=summary.warnings,
            stage_timings_ms=stage_timings_ms,
            latency_budget=latency_budget,
            artifact_writer=artifact_writer_snapshot,
            backpressure_policy=self.node.artifact_overload_policy,
        )
        if latency_budget.get('exceeded'):
            self.node._emit_event(
                'vision_latency_budget_exceeded',
                item_id=item_id,
                batch_id=batch_id,
                trace_id=trace_id,
                stage_timings_ms=stage_timings_ms,
                latency_budget=latency_budget,
            )
        if anno_receipt.status in {'dropped_overload', 'queue_overload'}:
            self.node._emit_event(
                'vision_backpressure_degraded',
                item_id=item_id,
                batch_id=batch_id,
                trace_id=trace_id,
                artifact_kind='annotated',
                policy=self.node.artifact_overload_policy,
                artifact_writer=artifact_writer_snapshot,
            )
        if raw_receipt.status == 'queue_overload':
            self.node._emit_event(
                'vision_backpressure_degraded',
                item_id=item_id,
                batch_id=batch_id,
                trace_id=trace_id,
                artifact_kind='raw',
                policy=self.node.artifact_overload_policy,
                artifact_writer=artifact_writer_snapshot,
            )
