from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class VisionLatencyBudget:
    """Latency budgets for the vision hot path."""

    bind_wait_ms: float = 80.0
    analyze_ms: float = 120.0
    artifact_persist_ms: float = 40.0
    publish_ms: float = 20.0
    total_ms: float = 200.0

    def evaluate(self, stage_timings_ms: dict[str, float]) -> dict[str, Any]:
        bind_wait = float(stage_timings_ms.get('bindWaitMs', 0.0) or 0.0)
        analyze = float(stage_timings_ms.get('analyzeMs', 0.0) or 0.0)
        artifact = float(stage_timings_ms.get('artifactPersistMs', 0.0) or 0.0)
        publish = float(stage_timings_ms.get('publishMs', 0.0) or 0.0)
        total = float(stage_timings_ms.get('totalMs', 0.0) or 0.0)
        exceeded_stages = [
            name
            for name, value, budget in (
                ('bindWaitMs', bind_wait, self.bind_wait_ms),
                ('analyzeMs', analyze, self.analyze_ms),
                ('artifactPersistMs', artifact, self.artifact_persist_ms),
                ('publishMs', publish, self.publish_ms),
                ('totalMs', total, self.total_ms),
            )
            if value > budget
        ]
        return {
            'budgetMs': {
                'bindWaitMs': round(self.bind_wait_ms, 3),
                'analyzeMs': round(self.analyze_ms, 3),
                'artifactPersistMs': round(self.artifact_persist_ms, 3),
                'publishMs': round(self.publish_ms, 3),
                'totalMs': round(self.total_ms, 3),
            },
            'actualMs': {
                'bindWaitMs': round(bind_wait, 3),
                'analyzeMs': round(analyze, 3),
                'artifactPersistMs': round(artifact, 3),
                'publishMs': round(publish, 3),
                'totalMs': round(total, 3),
            },
            'exceeded': bool(exceeded_stages),
            'exceededStages': exceeded_stages,
        }
