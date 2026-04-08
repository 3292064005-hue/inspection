from __future__ import annotations

import json
from pathlib import Path


class BaselineStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, baseline: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')

    def read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding='utf-8'))

    def compare(self, candidate: dict) -> dict:
        baseline = self.read()
        keys = sorted(set(baseline) | set(candidate))
        changes = {}
        for key in keys:
            if baseline.get(key) != candidate.get(key):
                changes[key] = {'baseline': baseline.get(key), 'candidate': candidate.get(key)}
        return changes
