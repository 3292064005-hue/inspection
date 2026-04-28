from __future__ import annotations

import json
import threading
import time
from typing import Callable

from inspection_utils.station_common import load_station_capability_expectation

from .bridge_base import BridgeSignal


class MockStationAdapter:
    def __init__(self, position_delay_sec: float, sort_delay_sec: float, *, capability_payload: dict[str, object] | None = None) -> None:
        """Create the synthetic station adapter.

        Args:
            position_delay_sec: Delay before POSITION_READY is emitted.
            sort_delay_sec: Delay before SORT_DONE is emitted.
            capability_payload: Optional capability payload derived from the
                station capability registry. When omitted, the adapter falls
                back to the historic mock capability shape.

        Boundary behavior:
            The payload is copied defensively so tests and launch code can pass
            mutable dictionaries without risking later mutation of adapter state.
        """
        self.position_delay_sec = position_delay_sec
        self.sort_delay_sec = sort_delay_sec
        self._callback: Callable[[BridgeSignal], None] | None = None
        expectation = load_station_capability_expectation('simulation_station_default', start=__file__)
        base_payload = expectation.to_payload(firmware_version='mock-v5', device_id='mock-station')
        if isinstance(capability_payload, dict):
            base_payload.update(capability_payload)
        self._capabilities = dict(base_payload)

    def set_callback(self, callback: Callable[[BridgeSignal], None]) -> None:
        self._callback = callback

    def _emit(self, state: str, seq: int = -1, **detail) -> None:
        if self._callback is not None:
            self._callback(BridgeSignal(state=state, seq=seq, detail=detail or None))

    def send_feed(self, seq: int, payload: bytes) -> None:
        detail = json.loads(payload.decode('utf-8') or '{}') if payload else {}
        threading.Thread(target=self._simulate_feed, args=(seq, detail), daemon=True).start()

    def _simulate_feed(self, seq: int, detail: dict) -> None:
        time.sleep(min(0.05, self.position_delay_sec / 4.0))
        self._emit('FEED_ACK', seq=seq, **detail)
        time.sleep(self.position_delay_sec)
        self._emit('POSITION_READY', seq=seq, **detail)

    def send_sort(self, seq: int, payload: bytes) -> None:
        detail = json.loads(payload.decode('utf-8') or '{}') if payload else {}
        threading.Thread(target=self._simulate_sort, args=(seq, detail), daemon=True).start()

    def _simulate_sort(self, seq: int, detail: dict) -> None:
        time.sleep(min(0.05, self.sort_delay_sec / 4.0))
        self._emit('SORT_ACK', seq=seq, **detail)
        time.sleep(self.sort_delay_sec)
        self._emit('SORT_DONE', seq=seq, **detail)

    def send_heartbeat(self, seq: int) -> None:
        self._emit('HEARTBEAT', seq=seq, message='mock_alive')

    def reset_fault(self, seq: int, payload: bytes = b'') -> None:
        self._emit('RESET_ACK', seq=seq, message='reset_complete')

    def query_capabilities(self, seq: int) -> None:
        self._emit('CAPABILITIES', seq=seq, **self._capabilities)

    def poll(self) -> None:
        return

    def close(self) -> None:
        return
