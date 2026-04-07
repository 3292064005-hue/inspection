from __future__ import annotations

from dataclasses import dataclass, field

from .cycle_runtime import CycleRuntime


@dataclass(slots=True)
class RuntimeContext:
    current: CycleRuntime = field(default_factory=CycleRuntime)
    profile_name: str = 'production'
    auto_mode_enabled: bool = True
    manual_history: list[dict[str, object]] = field(default_factory=list)

    def enter_manual(self) -> None:
        self.auto_mode_enabled = False

    def exit_manual(self) -> None:
        self.auto_mode_enabled = True
        self.current.artifacts.set('manual_exit', True)

    def record_manual_action(self, action: str, **extra: object) -> None:
        payload = {'action': action}
        payload.update(extra)
        self.manual_history.append(payload)

    def snapshot(self) -> dict[str, object]:
        return {
            'profile_name': self.profile_name,
            'auto_mode_enabled': self.auto_mode_enabled,
            'manual_history': list(self.manual_history[-16:]),
            'current': self.current.snapshot(),
        }
