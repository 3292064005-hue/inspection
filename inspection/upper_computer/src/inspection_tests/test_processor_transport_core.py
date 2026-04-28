from __future__ import annotations

from pathlib import Path

from vision_processing.processor_runtime import ProcessorArtifactRuntime, ProcessorExecutionRuntime


class _FrameBuffer:
    def __init__(self) -> None:
        self.pending: list[dict[str, object]] = []
        self.submissions: list[dict[str, object]] = []
        self.last_submit_status = 'queued'

    def submit_request(self, request: dict[str, object], monotonic_ts: float):
        self.submissions.append(dict(request))
        self.pending.append(dict(request))
        return None


class _Node:
    def __init__(self, *, active: bool, lifecycle_state: str) -> None:
        self._active = active
        self.lifecycle_state = lifecycle_state
        self.fallback_item_id = 7
        self.default_batch_id = 'B-DEFAULT'
        self.last_trace_id = ''
        self.last_trace_started_at = 0.0
        self.frame_buffer = _FrameBuffer()
        self.capture_pending_queue_size = 4
        self.capture_pending_overload_policy = 'drop_oldest'
        self.events: list[tuple[str, dict[str, object]]] = []
        self.artifact_backpressure_threshold = 0.9

    def is_active(self) -> bool:
        return self._active

    def _emit_event(self, event_type: str, **payload: object) -> None:
        self.events.append((event_type, dict(payload)))


def test_processor_runtime_exposes_canonical_capture_payload_entrypoint() -> None:
    root = Path(__file__).resolve().parents[2]
    runtime_text = (root / 'src' / 'vision_processing' / 'vision_processing' / 'processor_runtime.py').read_text(encoding='utf-8')
    node_text = (root / 'src' / 'vision_processing' / 'vision_processing' / 'processor_node.py').read_text(encoding='utf-8')
    assert 'def handle_capture_request_payload(self, payload: dict[str, Any]) -> None:' in runtime_text
    assert 'self.execution_runtime.handle_capture_request_payload(dict(payload))' in node_text
    assert 'legacy.data = event_to_json' not in node_text


def test_inactive_capture_requests_fail_closed_without_pending_queue_side_effects() -> None:
    node = _Node(active=False, lifecycle_state='INACTIVE')
    runtime = ProcessorExecutionRuntime(node, ProcessorArtifactRuntime(node))

    runtime.handle_capture_request_payload({'item_id': 3, 'trace_id': 'TRACE-3'})

    assert node.frame_buffer.submissions == []
    assert node.frame_buffer.pending == []
    assert node.events == [('vision_capture_ignored_inactive', {'trace_id': 'TRACE-3', 'item_id': 3, 'lifecycle_state': 'INACTIVE'})]


def test_active_capture_requests_still_flow_into_pending_queue() -> None:
    node = _Node(active=True, lifecycle_state='ACTIVE')
    runtime = ProcessorExecutionRuntime(node, ProcessorArtifactRuntime(node))

    runtime.handle_capture_request_payload({'item_id': 5, 'trace_id': 'TRACE-5'})

    assert len(node.frame_buffer.submissions) == 1
    assert node.frame_buffer.pending[0]['item_id'] == 5
    assert node.events[0][0] == 'vision_capture_pending'
