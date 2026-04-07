from __future__ import annotations

from pathlib import Path
from typing import Any

from inspection_logger.replay_executor import ReplayExecutor

from .evidence_repository import TraceEvidenceRepository
from .read_model_repository import ReadModelRepository


class ReplayService:
    def __init__(self, log_root: str | Path) -> None:
        self.log_root = Path(log_root)
        self.executor = ReplayExecutor(self.log_root)
        self.repository = TraceEvidenceRepository(self.log_root)
        self.read_model_repository = ReadModelRepository(self.log_root)

    def list_traces(
        self,
        *,
        batch_id: str = '',
        decision: str = '',
        q: str = '',
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        return self.read_model_repository.query_trace_page(batch_id=batch_id, decision=decision, q=q, limit=limit, offset=offset)

    def get_trace(self, trace_id: str) -> dict[str, Any]:
        summary = self.executor.replay_summary(trace_id)
        bundle = self.read_model_repository.trace_bundle(trace_id)
        summary.update(bundle)
        summary['traceId'] = trace_id
        return summary

    def compare_trace(self, trace_id: str) -> dict[str, Any]:
        payload = self.executor.compare_trace_to_summary(trace_id)
        payload['traceId'] = trace_id
        payload['bundle'] = self.read_model_repository.trace_bundle(trace_id)
        return payload
