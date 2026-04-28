from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from inspection_utils.model_common import CycleSummary


@dataclass(slots=True)
class TraceAccumulator:
    trace_id: str
    batch_id: str = ''
    item_id: int = -1
    decision: str = ''
    final_phase: str = ''
    final_status: str = 'UNKNOWN'
    cycle_time_sec: float = 0.0
    fail_point: str = ''
    phase_timings_ms: dict[str, float] = field(default_factory=dict)
    retry_counts: dict[str, int] = field(default_factory=dict)
    image_paths: dict[str, str] = field(default_factory=dict)

    def ingest(self, record: dict[str, Any]) -> None:
        self.batch_id = str(record.get('batch_id', self.batch_id))
        self.item_id = int(record.get('item_id', self.item_id))
        record_type = str(record.get('type', ''))
        if record_type == 'inspection_result':
            detail = record.get('detail', {})
            evidence = detail.get('evidence', {}) if isinstance(detail, dict) else {}
            raw_path = evidence.get('raw_path')
            ann_path = evidence.get('annotated_path')
            if raw_path:
                self.image_paths['raw'] = str(raw_path)
            if ann_path:
                self.image_paths['annotated'] = str(ann_path)
        elif record_type == 'cycle_finish':
            self.final_status = 'COMPLETED'
            self.decision = str(record.get('decision', self.decision))
            self.cycle_time_sec = float(record.get('cycle_time_sec', self.cycle_time_sec))
            self.phase_timings_ms = dict(record.get('phase_timings_ms', self.phase_timings_ms))
            self.final_phase = 'COUNT_UPDATE'
        elif record_type == 'fault':
            self.final_status = 'FAULT'
            self.fail_point = str(record.get('code', self.fail_point))
            self.final_phase = 'FAULT'
        elif record_type == 'fsm_transition':
            self.final_phase = str(record.get('to_phase', self.final_phase))
            retry_counts = record.get('retry_counts')
            if isinstance(retry_counts, dict):
                self.retry_counts = {str(k): int(v) for k, v in retry_counts.items()}

    def to_summary(self) -> dict[str, Any]:
        return CycleSummary(
            trace_id=self.trace_id,
            batch_id=self.batch_id,
            item_id=self.item_id,
            final_status=self.final_status,
            final_phase=self.final_phase,
            decision=self.decision,
            cycle_time_sec=self.cycle_time_sec,
            phase_timings_ms=self.phase_timings_ms,
            fail_point=self.fail_point,
            retry_counts=self.retry_counts,
            image_paths=self.image_paths,
        ).to_dict()
