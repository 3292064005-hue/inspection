from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from inspection_utils.logging_tools import safe_json_loads
from inspection_utils.paths import relative_artifact_path, resolve_runtime_path


def _safe_int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


class TraceEvidenceRepository:
    """Read trace/evidence bundles from runtime logging artifacts.

    The repository provides a backward-compatible read model over existing CSV
    and JSONL runtime logs. When richer indexes such as ``artifact_index`` are
    available, they are used. Otherwise the repository reconstructs the bundle
    from result rows, cycle summaries, and manifest entries.
    """

    def __init__(self, log_root: str | Path = 'logs/runtime') -> None:
        self.log_root = resolve_runtime_path(log_root, start=__file__)
        self.results_root = self.log_root / 'results'
        self.traces_root = self.log_root / 'traces'
        self.result_csv = self.results_root / 'result_log.csv'
        self.summary_jsonl = self.results_root / 'cycle_summary.jsonl'
        self.replay_manifest_jsonl = self.results_root / 'replay_manifest.jsonl'
        self.artifact_index_jsonl = self.results_root / 'artifact_index.jsonl'
        self.trace_index_csv = self.results_root / 'trace_index.csv'

    def _result_rows(self) -> list[dict[str, Any]]:
        if not self.result_csv.exists():
            return []
        with self.result_csv.open('r', encoding='utf-8', newline='') as handle:
            return list(csv.DictReader(handle))

    def _summary_map(self) -> dict[str, dict[str, Any]]:
        return {str(row.get('trace_id', '')): row for row in _read_jsonl(self.summary_jsonl)}

    def _manifest_map(self) -> dict[str, dict[str, Any]]:
        return {str(row.get('trace_id', '')): row for row in _read_jsonl(self.replay_manifest_jsonl)}

    def _artifact_map(self) -> dict[str, list[dict[str, Any]]]:
        payload: dict[str, list[dict[str, Any]]] = {}
        for row in _read_jsonl(self.artifact_index_jsonl):
            trace_id = str(row.get('trace_id', ''))
            if not trace_id:
                continue
            payload.setdefault(trace_id, []).append(dict(row))
        return payload

    def list_trace_ids(self) -> list[str]:
        """Collect all known trace identifiers from every supported evidence source.

        The repository may learn about a trace from summaries, replay manifests,
        result rows, raw trace event files, or the artifact index. The artifact
        index path is important for partially-written or backfilled runs where the
        evidence index exists before a summary/trace file is materialized.
        """
        trace_ids: set[str] = set()
        trace_ids.update(self._summary_map().keys())
        trace_ids.update(self._manifest_map().keys())
        trace_ids.update(self._artifact_map().keys())
        for row in self._result_rows():
            trace_id = str(row.get('trace_id', '')).strip()
            if trace_id:
                trace_ids.add(trace_id)
        for path in self.traces_root.glob('*.jsonl'):
            trace_ids.add(path.stem)
        return sorted(item for item in trace_ids if item)

    def result_row_for_trace(self, trace_id: str) -> dict[str, Any]:
        for row in self._result_rows():
            if str(row.get('trace_id', '')) == trace_id:
                return dict(row)
        return {}

    def result_row_for_id(self, result_id: str) -> dict[str, Any]:
        for row in self._result_rows():
            trace_id = str(row.get('trace_id', ''))
            candidate = trace_id or f"{row.get('batch_id', '')}-{row.get('item_id', '')}-{row.get('time', '')}"
            if candidate == result_id:
                return dict(row)
        return {}

    def load_trace_events(self, trace_id: str) -> list[dict[str, Any]]:
        trace_path = self.traces_root / f'{trace_id}.jsonl'
        return _read_jsonl(trace_path)

    def _artifact_payload(self, *, kind: str, path: str, trace_id: str, batch_id: str = '', item_id: int = -1, source: str = '') -> dict[str, Any]:
        normalized_path = str(path or '').replace('\\', '/').lstrip('/')
        return {
            'kind': str(kind),
            'path': normalized_path,
            'url': f"/artifacts/{relative_artifact_path(self.log_root, normalized_path)}" if normalized_path else '',
            'traceId': trace_id,
            'batchId': batch_id,
            'itemId': _safe_int(item_id, default=-1),
            'source': source or 'derived',
        }

    def collect_artifacts(self, trace_id: str, *, row: dict[str, Any] | None = None, detail: dict[str, Any] | None = None, summary: dict[str, Any] | None = None, manifest: dict[str, Any] | None = None, indexed_artifacts: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
        row = dict(row or {})
        detail = dict(detail or {})
        summary = dict(summary or {})
        manifest = dict(manifest or {})
        evidence = detail.get('evidence', {}) if isinstance(detail.get('evidence', {}), dict) else {}
        image_paths = summary.get('image_paths', {}) if isinstance(summary.get('image_paths', {}), dict) else {}
        seen: set[tuple[str, str]] = set()
        artifacts: list[dict[str, Any]] = []

        def add(kind: str, path: str, *, source: str) -> None:
            normalized_path = str(path or '').replace('\\', '/').lstrip('/')
            if not normalized_path:
                return
            key = (kind, normalized_path)
            if key in seen:
                return
            seen.add(key)
            artifacts.append(self._artifact_payload(
                kind=kind,
                path=normalized_path,
                trace_id=trace_id,
                batch_id=str(row.get('batch_id', summary.get('batch_id', ''))),
                item_id=_safe_int(row.get('item_id', summary.get('item_id', -1)), default=-1),
                source=source,
            ))

        add('raw', str(row.get('image_path', '')), source='result_csv')
        add('annotated', str(row.get('annotated_image_path', '')), source='result_csv')
        add('raw', str(evidence.get('raw_path', '')), source='detail_json')
        add('annotated', str(evidence.get('annotated_path', '')), source='detail_json')
        add('raw', str(image_paths.get('raw', '')), source='cycle_summary')
        add('annotated', str(image_paths.get('annotated', '')), source='cycle_summary')
        for record in manifest.get('artifacts', []) if isinstance(manifest.get('artifacts', []), list) else []:
            if not isinstance(record, dict):
                continue
            add(str(record.get('kind', 'artifact')), str(record.get('path', '')), source='replay_manifest')
        for record in list(indexed_artifacts or self._artifact_map().get(trace_id, [])):
            add(str(record.get('kind', 'artifact')), str(record.get('path', '')), source='artifact_index')
        return artifacts

    def _build_trace_bundle(
        self,
        *,
        trace_id: str,
        row: dict[str, Any] | None,
        summary: dict[str, Any] | None,
        manifest: dict[str, Any] | None,
        artifact_rows: list[dict[str, Any]] | None,
        events: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        row = dict(row or {})
        summary = dict(summary or {})
        manifest = dict(manifest or {})
        detail = safe_json_loads(row.get('detail_json', '') or '{}') if row else {}
        trace_path = self.traces_root / f'{trace_id}.jsonl'
        artifacts = self.collect_artifacts(
            trace_id,
            row=row,
            detail=detail,
            summary=summary,
            manifest={**manifest, 'artifacts': list((manifest or {}).get('artifacts', []))},
            indexed_artifacts=artifact_rows,
        )
        live_events = list(events or [])
        return {
            'traceId': trace_id,
            'traceUrl': f"/artifacts/{relative_artifact_path(self.log_root, trace_path)}" if trace_path.exists() else '',
            'eventCount': len(live_events),
            'events': live_events,
            'summary': summary,
            'runArtifacts': manifest.get('run_artifacts', {}),
            'configSnapshot': manifest.get('config_snapshot', {}),
            'artifacts': artifacts,
            'artifactCount': len(artifacts),
        }

    def trace_bundle(self, trace_id: str) -> dict[str, Any]:
        row = self.result_row_for_trace(trace_id)
        return self._build_trace_bundle(
            trace_id=trace_id,
            row=row,
            summary=self._summary_map().get(trace_id, {}),
            manifest=self._manifest_map().get(trace_id, {}),
            artifact_rows=self._artifact_map().get(trace_id, []),
            events=self.load_trace_events(trace_id),
        )

    def trace_bundles_for_ids(self, trace_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Build trace bundles for a batch of trace identifiers in one pass.

        Args:
            trace_ids: Ordered trace identifiers requested by the caller.

        Returns:
            Mapping from trace identifier to reconstructed evidence bundle.

        Raises:
            No exception is intentionally raised. Malformed rows are skipped and
            simply result in partial bundles.

        Boundary behavior:
            Duplicate trace identifiers are de-duplicated while preserving the
            caller-visible bundle payload for each unique trace id. Missing or
            empty identifiers are ignored.
        """
        unique_ids: list[str] = []
        seen_ids: set[str] = set()
        for trace_id in trace_ids:
            normalized = str(trace_id or '').strip()
            if not normalized or normalized in seen_ids:
                continue
            seen_ids.add(normalized)
            unique_ids.append(normalized)
        if not unique_ids:
            return {}

        result_rows = {str(row.get('trace_id', '')): dict(row) for row in self._result_rows() if str(row.get('trace_id', '')) in seen_ids}
        summary_map = self._summary_map()
        manifest_map = self._manifest_map()
        artifact_map = self._artifact_map()
        bundles: dict[str, dict[str, Any]] = {}
        for trace_id in unique_ids:
            bundles[trace_id] = self._build_trace_bundle(
                trace_id=trace_id,
                row=result_rows.get(trace_id, {}),
                summary=summary_map.get(trace_id, {}),
                manifest=manifest_map.get(trace_id, {}),
                artifact_rows=artifact_map.get(trace_id, []),
                events=self.load_trace_events(trace_id),
            )
        return bundles
