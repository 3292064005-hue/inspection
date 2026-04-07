from __future__ import annotations

from inspection_diagnostics.diagnostics_aggregator import DiagnosticsAggregator


def test_diagnostics_aggregator_builds_warn_and_error_levels() -> None:
    agg = DiagnosticsAggregator()
    agg.ingest_event({'type': 'vision_capture_done', 'processing_ms': 520.0, 'latency_budget': {'exceeded': True, 'exceededStages': ['totalMs']}, 'artifact_writer': {'queueUsage': 0.9, 'flushTimeouts': 0, 'failed': 0}})
    agg.ingest_event({'type': 'fault', 'code': 'FAULT_SENSOR'})
    agg.ingest_station_state({'heartbeat_ok': False, 'session': {'phase': 'DEGRADED'}})
    snap = agg.build_snapshot()
    assert snap['overall_level'] == 'ERROR'
    assert snap['channels']['vision']['level'] == 'WARN'
    assert snap['channels']['bridge']['level'] == 'ERROR'
    assert snap['channels']['faults']['values']['count'] == 1
    assert snap['channels']['vision_budget']['level'] == 'WARN'
    assert snap['channels']['artifact_backpressure']['level'] == 'WARN'
    assert snap['channels']['lifecycle_governance']['values']['matrix']
    assert snap['channels']['qos_governance']['values']['warnings']
