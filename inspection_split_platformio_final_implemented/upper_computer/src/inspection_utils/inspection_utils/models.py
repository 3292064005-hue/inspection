from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
import json


@dataclass(slots=True)
class WorkItem:
    item_id: int
    batch_id: str
    recipe_id: str
    trace_id: str
    cycle_index: int = 0


@dataclass(slots=True)
class DetectionSummary:
    valid: bool = True
    category: str = 'UNDECIDED'
    defect_type: str = 'NONE'
    score: float = 0.0
    qr_text: str = ''
    qr_ok: bool = False
    orientation_ok: bool = True
    color_name: str = 'unknown'
    color_ratio: float = 0.0
    warnings: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    trace_id: str = ''
    batch_id: str = ''
    item_id: int = -1
    recipe_id: str = ''
    processing_ms: float = 0.0

    @property
    def detail(self) -> dict[str, Any]:
        return {
            'warnings': self.warnings,
            'evidence': self.evidence,
            'metrics': self.metrics,
            'trace_id': self.trace_id,
            'processing_ms': self.processing_ms,
        }

    def to_detail_json(self) -> str:
        return json.dumps(self.detail, ensure_ascii=False, sort_keys=True)


@dataclass(slots=True)
class DecisionOutcome:
    decision: str
    reason: str
    action_code: int
    target_bin: str
    matched_rule_id: str = 'legacy_rule'
    explanation: list[str] = field(default_factory=list)
    matched_rule_priority: int = 0
    confidence: float = 1.0
    policy_notes: list[str] = field(default_factory=list)
    arbitration_notes: list[str] = field(default_factory=list)
    severity: str = 'info'

    def to_dict(self) -> dict[str, Any]:
        return {
            'decision': self.decision,
            'reason': self.reason,
            'action_code': self.action_code,
            'target_bin': self.target_bin,
            'matched_rule_id': self.matched_rule_id,
            'matched_rule_priority': self.matched_rule_priority,
            'confidence': self.confidence,
            'explanation': list(self.explanation),
            'policy_notes': list(self.policy_notes),
            'arbitration_notes': list(self.arbitration_notes),
            'severity': self.severity,
        }


@dataclass(slots=True)
class TraceEvent:
    trace_id: str
    event_type: str
    message: str
    phase: str = ''
    item_id: int = -1
    batch_id: str = ''
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'trace_id': self.trace_id,
            'event_type': self.event_type,
            'message': self.message,
            'phase': self.phase,
            'item_id': self.item_id,
            'batch_id': self.batch_id,
            'extra': self.extra,
        }


@dataclass(slots=True)
class CycleMetrics:
    trace_id: str
    item_id: int
    batch_id: str
    timings_ms: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'trace_id': self.trace_id,
            'item_id': self.item_id,
            'batch_id': self.batch_id,
            'timings_ms': self.timings_ms,
        }


@dataclass(slots=True)
class CycleSummary:
    trace_id: str
    batch_id: str
    item_id: int
    final_status: str
    final_phase: str
    decision: str = ''
    cycle_time_sec: float = 0.0
    phase_timings_ms: dict[str, float] = field(default_factory=dict)
    fail_point: str = ''
    retry_counts: dict[str, int] = field(default_factory=dict)
    image_paths: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            'trace_id': self.trace_id,
            'batch_id': self.batch_id,
            'item_id': self.item_id,
            'final_status': self.final_status,
            'final_phase': self.final_phase,
            'decision': self.decision,
            'cycle_time_sec': self.cycle_time_sec,
            'phase_timings_ms': self.phase_timings_ms,
            'fail_point': self.fail_point,
            'retry_counts': self.retry_counts,
            'image_paths': self.image_paths,
        }
