from __future__ import annotations

from dataclasses import dataclass

STX = 0x02
ETX = 0x03
PROTOCOL_VERSION = 0x01

CMD_FEED_ONE = 0x10
CMD_SORT_TO_BIN = 0x20
CMD_QUERY_STATUS = 0x30
CMD_RESET_FAULT = 0x40
CMD_QUERY_CAPABILITIES = 0x41
CMD_HEARTBEAT = 0x7E

RSP_ACK = 0x80
RSP_NACK = 0x81
RSP_POSITION_READY = 0x90
RSP_SORT_DONE = 0x91
RSP_HEARTBEAT = 0x92
RSP_CAPABILITIES = 0x93
RSP_FAULT = 0xE0


def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


@dataclass(slots=True)
class Frame:
    cmd: int
    seq: int
    payload: bytes = b''

    def to_bytes(self) -> bytes:
        body = bytes([self.cmd & 0xFF, self.seq & 0xFF, len(self.payload) & 0xFF]) + self.payload
        return bytes([STX]) + body + bytes([crc8(body), ETX])

    @classmethod
    def from_bytes(cls, frame: bytes) -> 'Frame':
        if len(frame) < 5 or frame[0] != STX or frame[-1] != ETX:
            raise ValueError('invalid frame boundary')
        body = frame[1:-2]
        if crc8(body) != frame[-2]:
            raise ValueError('crc mismatch')
        cmd, seq, length = body[0], body[1], body[2]
        payload = body[3:3 + length]
        if len(payload) != length:
            raise ValueError('payload length mismatch')
        return cls(cmd=cmd, seq=seq, payload=payload)


class FrameStreamParser:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[Frame]:
        self._buffer.extend(chunk)
        frames: list[Frame] = []
        while True:
            if STX not in self._buffer:
                self._buffer.clear()
                return frames
            stx_index = self._buffer.index(STX)
            if stx_index:
                del self._buffer[:stx_index]
            if len(self._buffer) < 5:
                return frames
            length = self._buffer[3]
            total_len = 1 + 3 + length + 1 + 1
            if len(self._buffer) < total_len:
                return frames
            candidate = bytes(self._buffer[:total_len])
            del self._buffer[:total_len]
            try:
                frames.append(Frame.from_bytes(candidate))
            except ValueError:
                continue


def build_frame(cmd: int, seq: int, payload: bytes = b'') -> bytes:
    return Frame(cmd=cmd, seq=seq, payload=payload).to_bytes()


def parse_frame(frame: bytes) -> tuple[int, int, bytes]:
    parsed = Frame.from_bytes(frame)
    return parsed.cmd, parsed.seq, parsed.payload
