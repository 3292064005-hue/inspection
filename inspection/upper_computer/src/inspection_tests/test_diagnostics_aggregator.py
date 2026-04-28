from __future__ import annotations

from inspection_diagnostics.diagnostics_aggregator import DiagnosticsAggregator


def test_diagnostics_aggregator_builds_warn_and_error_levels() -> None:
    agg = DiagnosticsAggregator()
    agg.ingest_event({'type': 'vision_capture_done', 'processing_ms': 520.0, 'latency_budget': {'exceeded': True, 'exceededStages': ['totalMs']}, 'artifact_writer': {'queueUsage': 0.9, 'flushTimeouts': 0, 'failed': 0}})
    agg.ingest_event({'type': 'fault', 'code': 'FAULT_SENSOR'})
    agg.ingest_station_state({'heartbeat_ok': False, 'session': {'phase': 'DEGRADED'}})
    agg.ingest_camera_status({'status': 'camera_read_failed', 'statusReason': 'camera_timeout', 'readFailures': 2})
    agg.ingest_result_raw({'type': 'vision_result_raw', 'trace_id': 'trace-1', 'warnings': ['low_contrast'], 'processing_ms': 520.0})
    agg.ingest_annotated_frame({'frameId': 'frame-0001', 'width': 640, 'height': 480, 'encoding': 'bgr8'})
    snap = agg.build_snapshot()
    assert snap['overall_level'] == 'ERROR'
    assert snap['channels']['vision']['level'] == 'WARN'
    assert snap['channels']['bridge']['level'] == 'ERROR'
    assert snap['channels']['camera']['level'] == 'ERROR'
    assert snap['channels']['vision_debug']['level'] == 'WARN'
    assert snap['channels']['annotated_stream']['values']['frameCount'] == 1
    assert snap['channels']['faults']['values']['count'] == 1
    assert snap['channels']['vision_budget']['level'] == 'WARN'
    assert snap['channels']['artifact_backpressure']['level'] == 'WARN'
    assert snap['channels']['artifact_quality']['level'] == 'OK'
    assert snap['channels']['artifact_quality']['values']['annotatedRetentionPolicy'] == 'best_effort'
    assert snap['channels']['lifecycle_governance']['values']['matrix']
    assert snap['channels']['qos_governance']['values']['warnings']


def test_diagnostics_aggregator_treats_parse_failed_debug_payload_as_error() -> None:
    agg = DiagnosticsAggregator()
    agg.ingest_result_raw({'type': 'vision_result_raw_parse_failed', 'raw': '{oops'})
    snap = agg.build_snapshot()
    assert snap['channels']['vision_debug']['level'] == 'ERROR'
    assert snap['channels']['vision_debug']['values']['available'] is True


def test_diagnostics_aggregator_marks_artifact_quality_degraded_when_annotated_frames_are_dropped() -> None:
    agg = DiagnosticsAggregator()
    agg.ingest_event({'type': 'vision_capture_done', 'processing_ms': 100.0, 'artifact_writer': {'queueUsage': 0.92, 'flushTimeouts': 0, 'failed': 0, 'droppedOverload': 3}})
    snap = agg.build_snapshot()
    assert snap['channels']['artifact_quality']['level'] == 'WARN'
    assert snap['channels']['artifact_quality']['values']['degraded'] is True
    assert snap['channels']['artifact_quality']['values']['droppedOverload'] == 3
