from pathlib import Path


def test_station_bridge_session_coordinator_exists_and_node_uses_it() -> None:
    root = Path(__file__).resolve().parents[2]
    bridge = root / 'src' / 'station_bridge' / 'station_bridge'
    coordinator = (bridge / 'session_coordinator.py').read_text(encoding='utf-8')
    node = (bridge / 'station_bridge_node.py').read_text(encoding='utf-8')
    assert 'class BridgeSessionCoordinator' in coordinator
    assert 'self.coordinator = BridgeSessionCoordinator(self)' in node
    assert 'self.coordinator.on_feed_request' in node
