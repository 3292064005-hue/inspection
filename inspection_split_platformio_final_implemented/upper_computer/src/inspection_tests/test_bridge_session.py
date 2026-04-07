from station_bridge.reconnect_policy import ReconnectPolicy
from station_bridge.reset_sync import ResetSync
from station_bridge.session_state import BridgeSession, SessionPhase


def test_bridge_session_flow_and_reconnect_delay():
    session = BridgeSession(protocol_version=1)
    session.mark_handshaking()
    session.mark_ready(device_id='DEV1', capabilities={'features': ['SORT_ACK']})
    assert session.phase == SessionPhase.READY
    assert session.device_id == 'DEV1'
    session.mark_degraded()
    assert session.phase == SessionPhase.DEGRADED
    delay = ReconnectPolicy(base_delay_sec=0.5, max_delay_sec=2.0).delay_for_attempt(3)
    assert 0.5 <= delay <= 2.0
    sync = ResetSync()
    sync.start(7)
    assert sync.pending is True and sync.seq == 7
    sync.complete()
    assert sync.pending is False
