from __future__ import annotations

import csv
from pathlib import Path

from inspection_utils.logging_common import append_jsonl, utc_now_str


class TraceStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        (self.root / 'events').mkdir(parents=True, exist_ok=True)
        (self.root / 'results').mkdir(parents=True, exist_ok=True)
        (self.root / 'traces').mkdir(parents=True, exist_ok=True)
        (self.root / 'config_snapshot').mkdir(parents=True, exist_ok=True)
        self.event_path = self.root / 'events' / 'event_log.jsonl'
        self.result_csv = self.root / 'results' / 'result_log.csv'
        self.trace_index_csv = self.root / 'results' / 'trace_index.csv'
        self.summary_path = self.root / 'results' / 'cycle_summary.jsonl'
        self.manifest_path = self.root / 'results' / 'replay_manifest.jsonl'
        self.artifact_index_path = self.root / 'results' / 'artifact_index.jsonl'
        self.run_artifacts: dict[str, object] = {}
        self._ensure_csv(self.result_csv, ['time', 'trace_id', 'batch_id', 'item_id', 'recipe_id', 'category', 'defect_type', 'score', 'qr_ok', 'qr_text', 'orientation_ok', 'color_name', 'color_ratio', 'image_path', 'annotated_image_path', 'detail_json'])
        self._ensure_csv(self.trace_index_csv, ['time', 'trace_id', 'batch_id', 'item_id', 'phase_or_type', 'summary'])

    def _ensure_csv(self, path: Path, header: list[str]) -> None:
        if path.exists():
            return
        with path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(header)

    def set_run_artifacts(self, **artifacts: object) -> None:
        self.run_artifacts.update(artifacts)

    def trace_path(self, trace_id: str) -> Path:
        safe = trace_id or 'UNTRACED'
        return self.root / 'traces' / f'{safe}.jsonl'

    def append_event(self, record: dict) -> None:
        append_jsonl(self.event_path, record)

    def append_trace(self, trace_id: str, record: dict) -> None:
        append_jsonl(self.trace_path(trace_id), record)
        with self.trace_index_csv.open('a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([utc_now_str(), trace_id, record.get('batch_id', ''), record.get('item_id', -1), record.get('type', ''), str(record)])

    def append_result_row(self, row: list[object]) -> None:
        with self.result_csv.open('a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(row)

    def append_artifact_record(self, *, trace_id: str, batch_id: str, item_id: int, kind: str, path: str, meta: dict | None = None) -> None:
        append_jsonl(self.artifact_index_path, {
            'time': utc_now_str(),
            'trace_id': trace_id,
            'batch_id': batch_id,
            'item_id': item_id,
            'kind': kind,
            'path': path,
            'meta': dict(meta or {}),
        })

    def append_summary(self, record: dict) -> None:
        append_jsonl(self.summary_path, record)
        image_paths = record.get('image_paths', {}) if isinstance(record.get('image_paths', {}), dict) else {}
        artifacts = []
        for kind, path in (('raw', image_paths.get('raw', '')), ('annotated', image_paths.get('annotated', ''))):
            if path:
                artifacts.append({'kind': kind, 'path': str(path)})
        append_jsonl(self.manifest_path, {
            'time': utc_now_str(),
            'trace_id': record.get('trace_id', ''),
            'trace_path': str(self.trace_path(str(record.get('trace_id', '')))),
            'summary': record,
            'run_artifacts': dict(self.run_artifacts),
            'artifacts': artifacts,
            'config_snapshot': {
                'recipe_path': str(self.root / 'config_snapshot' / 'recipe.yaml'),
                'station_path': str(self.root / 'config_snapshot' / 'station.yaml'),
                'camera_path': str(self.root / 'config_snapshot' / 'camera.yaml'),
            },
        })
