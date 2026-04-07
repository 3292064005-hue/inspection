import time

from station_bridge.watchdog import BridgeWatchdog


def test_watchdog_expires():
    wd = BridgeWatchdog(timeout_sec=0.01)
    wd.arm()
    time.sleep(0.02)
    assert wd.expired() is True
