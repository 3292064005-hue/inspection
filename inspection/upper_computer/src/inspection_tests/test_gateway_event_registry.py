from __future__ import annotations

from pathlib import Path

from inspection_hmi_gateway.event_catalog import gateway_event_registry, validate_gateway_event_registry


def test_required_gateway_events_have_aligned_producer_consumer_runtime_anchors() -> None:
    project_root = Path(__file__).resolve().parents[3]
    registry = gateway_event_registry()
    issues = validate_gateway_event_registry(project_root=project_root, registry=registry)
    assert issues == []
