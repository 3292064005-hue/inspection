from vision_processing.frame_binding import FrameBindingBuffer, FrameSample


def _frame(frame_index: int, monotonic_ts: float) -> FrameSample:
    return FrameSample(frame_index=frame_index, monotonic_ts=monotonic_ts, stamp={'sec': frame_index}, header={'frame_id': frame_index}, image={'frame': frame_index})


def test_bind_prefers_first_frame_after_request() -> None:
    buffer = FrameBindingBuffer(fallback_window_sec=0.2)
    buffer.push_frame(_frame(0, 1.0))
    assert buffer.submit_request({'trace_id': 'T-1'}, monotonic_ts=1.1) is None
    ready = buffer.push_frame(_frame(1, 1.2))
    assert len(ready) == 1 and ready[0][0]['trace_id'] == 'T-1' and ready[0][1].frame_index == 1


def test_bind_can_use_recent_fallback_frame() -> None:
    buffer = FrameBindingBuffer(fallback_window_sec=0.2)
    buffer.push_frame(_frame(2, 2.0))
    sample = buffer.submit_request({'trace_id': 'T-2', 'allow_cached_frame': True}, monotonic_ts=2.1)
    assert sample is not None and sample.frame_index == 2


def test_pending_queue_drops_oldest_when_capacity_is_reached() -> None:
    buffer = FrameBindingBuffer(fallback_window_sec=0.2, max_pending_requests=2, pending_overload_policy='drop_oldest')
    assert buffer.submit_request({'trace_id': 'T-1'}, monotonic_ts=1.0) is None
    assert buffer.submit_request({'trace_id': 'T-2'}, monotonic_ts=1.1) is None
    assert buffer.submit_request({'trace_id': 'T-3'}, monotonic_ts=1.2) is None
    assert buffer.last_submit_status == 'drop_oldest'
    assert [item.request['trace_id'] for item in buffer.pending] == ['T-2', 'T-3']


def test_pending_queue_can_drop_newest_when_configured() -> None:
    buffer = FrameBindingBuffer(fallback_window_sec=0.2, max_pending_requests=1, pending_overload_policy='drop_newest')
    assert buffer.submit_request({'trace_id': 'T-1'}, monotonic_ts=1.0) is None
    assert buffer.submit_request({'trace_id': 'T-2'}, monotonic_ts=1.1) is None
    assert buffer.last_submit_status == 'drop_newest'
    assert [item.request['trace_id'] for item in buffer.pending] == ['T-1']
