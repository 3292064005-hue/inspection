from __future__ import annotations

import json
from pathlib import Path

from .diff_reporter import diff_summaries
from .replay_validator import validate_trace_events


class ReplayExecutor:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.manifest_path = self.root / 'results' / 'replay_manifest.jsonl'
        self.summary_path = self.root / 'results' / 'cycle_summary.jsonl'

    def list_traces(self) -> list[str]:
        if not self.manifest_path.exists():
            return []
        traces: list[str] = []
        for line in self.manifest_path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            trace_id = str(record.get('trace_id', ''))
            if trace_id:
                traces.append(trace_id)
        return traces

    def manifest_entry(self, trace_id: str) -> dict:
        if not self.manifest_path.exists():
            return {}
        for line in self.manifest_path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if str(record.get('trace_id', '')) == trace_id:
                return record
        return {}

    def load_trace(self, trace_id: str) -> list[dict]:
        trace_path = self.root / 'traces' / f'{trace_id}.jsonl'
        if not trace_path.exists():
            return []
        return [json.loads(line) for line in trace_path.read_text(encoding='utf-8').splitlines() if line.strip()]

    def load_summaries(self) -> dict[str, dict]:
        if not self.summary_path.exists():
            return {}
        summaries: dict[str, dict] = {}
        for line in self.summary_path.read_text(encoding='utf-8').splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            trace_id = str(record.get('trace_id', ''))
            if trace_id:
                summaries[trace_id] = record
        return summaries

    def replay_summary(self, trace_id: str) -> dict:
        events = self.load_trace(trace_id)
        if not events:
            return {'trace_id': trace_id, 'status': 'MISSING'}
        phases = [event.get('to_phase') for event in events if event.get('type') == 'fsm_transition']
        last_event = events[-1]
        validation = validate_trace_events(trace_id, events).to_dict()
        manifest = self.manifest_entry(trace_id)
        return {
            'trace_id': trace_id,
            'event_count': len(events),
            'phases': [phase for phase in phases if phase],
            'final_type': last_event.get('type', ''),
            'final_record': last_event,
            'validation': validation,
            'run_artifacts': manifest.get('run_artifacts', {}),
        }

    def compare_trace_to_summary(self, trace_id: str) -> dict:
        summaries = self.load_summaries()
        trace_summary = self.replay_summary(trace_id)
        stored = summaries.get(trace_id, {})
        normalized_trace = {
            'trace_id': trace_id,
            'final_status': 'FAULT' if trace_summary.get('final_type') == 'fault' else ('COMPLETED' if trace_summary.get('final_type') == 'cycle_finish' else 'UNKNOWN'),
            'event_count': trace_summary.get('event_count', 0),
            'final_type': trace_summary.get('final_type', ''),
        }
        normalized_stored = {
            'trace_id': trace_id,
            'final_status': stored.get('final_status', ''),
            'decision': stored.get('decision', ''),
            'final_phase': stored.get('final_phase', ''),
        }
        diff = diff_summaries(normalized_stored, normalized_trace)
        diff['run_artifacts'] = trace_summary.get('run_artifacts', {})
        return diff
