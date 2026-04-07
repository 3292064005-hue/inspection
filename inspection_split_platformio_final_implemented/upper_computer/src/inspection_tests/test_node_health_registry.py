from __future__ import annotations

from inspection_supervisor.node_health_registry import NodeHealthRegistry


def test_registry_tracks_stale_and_missing_nodes() -> None:
    registry = NodeHealthRegistry(expected_nodes=['camera_node', 'inspection_fsm_node'])
    registry.ingest_event('camera_node', now=1.0, event_type='heartbeat', state='ACTIVE')
    status = registry.overall_status(now=1.5, timeout_sec=1.0)
    assert status['healthy'] is False
    assert status['missing_active_nodes'] == ['inspection_fsm_node']
    assert status['stale_nodes'] == ['inspection_fsm_node']


def test_registry_all_required_active() -> None:
    registry = NodeHealthRegistry(expected_nodes=['camera_node', 'inspection_fsm_node'])
    registry.ingest_event('camera_node', now=1.0, event_type='heartbeat', state='ACTIVE')
    registry.ingest_event('inspection_fsm_node', now=1.2, event_type='heartbeat', state='READY')
    status = registry.overall_status(now=1.5, timeout_sec=1.0)
    assert status['healthy'] is True
    assert registry.all_required_active() is True
