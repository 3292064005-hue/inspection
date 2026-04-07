from inspection_diagnostics.diagnostic_adapter import snapshot_to_statuses


def test_snapshot_to_statuses_includes_overall_and_channels():
    statuses = snapshot_to_statuses(
        {
            'overall_level': 'WARN',
            'summary': 'degraded',
            'channels': {
                'bridge': {'level': 'ERROR', 'message': 'bridge down', 'values': {'heartbeat_ok': False}},
                'vision': {'level': 'OK', 'message': 'nominal', 'values': {'avg_processing_ms': 12.5}},
            },
        }
    )
    assert statuses[0]['name'] == 'inspection/overall'
    assert statuses[0]['level'] == 1
    assert any(status['name'] == 'inspection/bridge' and status['level'] == 2 for status in statuses)
