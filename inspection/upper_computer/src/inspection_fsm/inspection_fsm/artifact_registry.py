from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ArtifactRegistry:
    """Stores cycle-scoped evidence and references in one place."""

    refs: dict[str, Any] = field(default_factory=dict)

    def clear(self) -> None:
        self.refs.clear()

    def set(self, key: str, value: Any) -> None:
        self.refs[key] = value

    def update(self, mapping: dict[str, Any]) -> None:
        self.refs.update(mapping)

    def get(self, key: str, default: Any = None) -> Any:
        return self.refs.get(key, default)

    def snapshot(self) -> dict[str, Any]:
        return dict(self.refs)
