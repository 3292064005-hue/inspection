from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import time


class SessionPhase(str, Enum):
    INIT = 'INIT'
    HANDSHAKING = 'HANDSHAKING'
    READY = 'READY'
    DEGRADED = 'DEGRADED'
    RESETTING = 'RESETTING'
    RECONNECTING = 'RECONNECTING'


@dataclass(slots=True)
class BridgeSession:
    session_id: int = 1
    generation: int = 1
    phase: SessionPhase = SessionPhase.INIT
    protocol_version: int = 1
    device_id: str = ''
    capabilities: dict[str, object] = field(default_factory=dict)
    last_handshake_monotonic: float = 0.0
    reconnect_attempts: int = 0

    def new_session(self) -> None:
        self.session_id += 1
        self.generation += 1
        self.phase = SessionPhase.INIT
        self.device_id = ''
        self.capabilities = {}
        self.last_handshake_monotonic = 0.0

    def mark_handshaking(self) -> None:
        self.phase = SessionPhase.HANDSHAKING

    def mark_ready(self, *, device_id: str = '', capabilities: dict[str, object] | None = None) -> None:
        self.phase = SessionPhase.READY
        self.device_id = device_id
        if capabilities is not None:
            self.capabilities = dict(capabilities)
        self.last_handshake_monotonic = time.monotonic()
        self.reconnect_attempts = 0

    def mark_degraded(self) -> None:
        self.phase = SessionPhase.DEGRADED

    def mark_resetting(self) -> None:
        self.phase = SessionPhase.RESETTING

    def mark_reconnecting(self) -> None:
        self.phase = SessionPhase.RECONNECTING
        self.reconnect_attempts += 1

    def snapshot(self) -> dict[str, object]:
        return {
            'session_id': self.session_id,
            'generation': self.generation,
            'phase': self.phase.value,
            'protocol_version': self.protocol_version,
            'device_id': self.device_id,
            'capabilities': dict(self.capabilities),
            'reconnect_attempts': self.reconnect_attempts,
            'last_handshake_monotonic': round(self.last_handshake_monotonic, 6),
        }
