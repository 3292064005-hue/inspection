from __future__ import annotations

import json
from typing import Callable

try:
    import serial  # type: ignore
except Exception:  # pragma: no cover
    serial = None

from inspection_utils.protocol import (
    CMD_FEED_ONE,
    CMD_HEARTBEAT,
    CMD_QUERY_CAPABILITIES,
    CMD_RESET_FAULT,
    CMD_SORT_TO_BIN,
    Frame,
    RSP_ACK,
    RSP_CAPABILITIES,
    RSP_FAULT,
    RSP_HEARTBEAT,
    RSP_NACK,
    RSP_POSITION_READY,
    RSP_SORT_DONE,
)
from .bridge_base import BridgeSignal
from .rx_parser import RXParser


class SerialStationAdapter:
    def __init__(self, port: str, baudrate: int) -> None:
        if serial is None:  # pragma: no cover
            raise RuntimeError('pyserial is not available')
        self._serial = serial.Serial(port, baudrate, timeout=0.05)
        self._parser = RXParser()
        self._callback: Callable[[BridgeSignal], None] | None = None

    def set_callback(self, callback: Callable[[BridgeSignal], None]) -> None:
        self._callback = callback

    def _write(self, cmd: int, seq: int, payload: bytes) -> None:
        self._serial.write(Frame(cmd=cmd, seq=seq, payload=payload).to_bytes())

    def send_feed(self, seq: int, payload: bytes) -> None:
        self._write(CMD_FEED_ONE, seq, payload)

    def send_sort(self, seq: int, payload: bytes) -> None:
        self._write(CMD_SORT_TO_BIN, seq, payload)

    def send_heartbeat(self, seq: int) -> None:
        self._write(CMD_HEARTBEAT, seq, b'HB')

    def reset_fault(self, seq: int, payload: bytes = b'') -> None:
        self._write(CMD_RESET_FAULT, seq, payload)

    def query_capabilities(self, seq: int) -> None:
        self._write(CMD_QUERY_CAPABILITIES, seq, b'CAP?')

    def poll(self) -> None:
        chunk = self._serial.read(256)
        if not chunk:
            return
        for frame in self._parser.feed(chunk):
            self._handle_frame(frame)

    def _emit(self, state: str, seq: int, **detail) -> None:
        if self._callback is not None:
            self._callback(BridgeSignal(state=state, seq=seq, detail=detail or None))

    def _handle_frame(self, frame: Frame) -> None:
        payload = {}
        if frame.payload:
            try:
                payload = json.loads(frame.payload.decode('utf-8'))
            except Exception:
                payload = {'raw_payload': list(frame.payload)}
        if frame.cmd == RSP_ACK:
            phase = str(payload.get('phase', '')).upper()
            if phase == 'SORT':
                state = 'SORT_ACK'
            elif phase == 'RESET':
                state = 'RESET_ACK'
            else:
                state = 'FEED_ACK'
            self._emit(state, frame.seq, **payload)
        elif frame.cmd == RSP_POSITION_READY:
            self._emit('POSITION_READY', frame.seq, **payload)
        elif frame.cmd == RSP_SORT_DONE:
            self._emit('SORT_DONE', frame.seq, **payload)
        elif frame.cmd == RSP_HEARTBEAT:
            self._emit('HEARTBEAT', frame.seq, **payload)
        elif frame.cmd == RSP_CAPABILITIES:
            self._emit('CAPABILITIES', frame.seq, **payload)
        elif frame.cmd == RSP_FAULT:
            self._emit('FAULT', frame.seq, **payload)
        elif frame.cmd == RSP_NACK:
            self._emit('FAULT', frame.seq, fault_code='FAULT_NACK', **payload)

    def close(self) -> None:
        self._serial.close()
