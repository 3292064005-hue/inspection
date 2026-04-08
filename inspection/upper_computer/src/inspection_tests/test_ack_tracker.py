from station_bridge.ack_tracker import AckTracker


def test_ack_tracker_register_ack_done_flow():
    tracker = AckTracker()
    pending = tracker.register(3, 'sort', 'TRACE-1', 1, 'BATCH')
    assert pending.seq == 3
    tracker.mark_ack(3)
    assert pending.acked is True
    tracker.mark_done(3)
    assert tracker.oldest_pending() is None
    snapshot = tracker.snapshot()
    assert any(item['seq'] == 3 and item['state'] == 'done' for item in snapshot)


def test_ack_tracker_cancel_by_trace_keeps_history():
    tracker = AckTracker()
    tracker.register(1, 'feed', 'TRACE-A', 1, 'BATCH')
    tracker.register(2, 'sort', 'TRACE-A', 1, 'BATCH')
    cancelled = tracker.cancel_by_trace('TRACE-A')
    assert len(cancelled) == 2
    assert tracker.oldest_pending() is None
    snapshot = tracker.snapshot()
    assert sum(1 for item in snapshot if item['state'] == 'cancelled') >= 2


def test_ack_tracker_marks_timeout_and_orphan():
    tracker = AckTracker()
    tracker.register(9, 'feed', 'TRACE-Z', 9, 'BATCH')
    timeout_items = tracker.stale(0.0, mark=True)
    assert len(timeout_items) == 1
    assert timeout_items[0].state == 'timeout_expired'
    orphan = tracker.record_orphan_response(10, 'sort', reason='late_done')
    assert orphan.state == 'orphaned'
