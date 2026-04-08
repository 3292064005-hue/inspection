from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SupervisorMode(str, Enum):
    STOPPED = 'STOPPED'
    AUTO = 'AUTO'
    PAUSED = 'PAUSED'
    MAINTENANCE = 'MAINTENANCE'
    BENCHMARK = 'BENCHMARK'


@dataclass(slots=True)
class ModeManager:
    current_mode: SupervisorMode = SupervisorMode.STOPPED
    allowed_modes: set[SupervisorMode] = field(default_factory=lambda: {
        SupervisorMode.STOPPED,
        SupervisorMode.AUTO,
        SupervisorMode.PAUSED,
        SupervisorMode.MAINTENANCE,
        SupervisorMode.BENCHMARK,
    })
    history: list[dict[str, str]] = field(default_factory=list)

    def request(self, mode: str | SupervisorMode, reason: str = '') -> bool:
        target = mode if isinstance(mode, SupervisorMode) else SupervisorMode(str(mode).upper())
        if target not in self.allowed_modes:
            return False
        previous = self.current_mode
        self.current_mode = target
        self.history.append({'from': previous.value, 'to': target.value, 'reason': reason})
        return True

    def is_auto_like(self) -> bool:
        return self.current_mode in {SupervisorMode.AUTO, SupervisorMode.BENCHMARK}

    def is_manual_like(self) -> bool:
        return self.current_mode == SupervisorMode.MAINTENANCE

    def snapshot(self) -> dict[str, object]:
        return {
            'current_mode': self.current_mode.value,
            'allowed_modes': sorted(mode.value for mode in self.allowed_modes),
            'history': list(self.history[-20:]),
        }
