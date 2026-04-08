from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZIP_DEFLATED, ZipFile

from inspection_utils.paths import resolve_log_artifact_path, resolve_runtime_path

from .recipe_store import RecipeStore
from .result_store import ResultStore


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec='seconds').replace('+00:00', 'Z')


def _safe_name(value: str) -> str:
    cleaned = ''.join(ch if ch.isalnum() or ch in {'-', '_', '.'} else '_' for ch in value.strip())
    return cleaned or 'batch-export'


@dataclass(slots=True)
class ExportArtifacts:
    export_path: Path
    item_count: int
    trace_count: int


class BatchExportService:
    def __init__(self, *, log_root: str | Path = 'logs/runtime', result_store: ResultStore, recipe_store: RecipeStore) -> None:
        self.log_root = resolve_runtime_path(log_root, start=__file__)
        self.result_store = result_store
        self.recipe_store = recipe_store
        self.exports_root = self.log_root / 'exports'
        self.exports_root.mkdir(parents=True, exist_ok=True)

    def export_batch(self, batch_id: str) -> ExportArtifacts:
        batch_id = str(batch_id).strip()
        if not batch_id:
            raise ValueError('batch_id is required')
        items = self.result_store.query_results(batch_id=batch_id)
        result_ids = self.result_store.result_ids_for_batch(batch_id)
        trace_bundles = self.result_store.trace_bundles_for_batch(batch_id)
        trace_ids = sorted(set(trace_bundles.keys()) or {str(item.get('traceId', '')) for item in items if item.get('traceId')})
        return self._export_scope(scope='batch', scope_id=batch_id, items=items, result_ids=result_ids, trace_ids=trace_ids, trace_bundles=trace_bundles)

    def export_result(self, result_id: str) -> ExportArtifacts:
        result_id = str(result_id).strip()
        if not result_id:
            raise ValueError('result_id is required')
        detail = self.result_store.get_result(result_id)
        if detail is None:
            raise ValueError('result_not_found')
        result_ids = [str(detail.get('id', result_id))]
        trace_id = str(detail.get('traceId', ''))
        trace_bundle = self.result_store.trace_bundle_for_result(result_id)
        trace_bundles = {trace_id: trace_bundle} if trace_id else {}
        return self._export_scope(scope='result', scope_id=result_ids[0], items=[detail], result_ids=result_ids, trace_ids=[trace_id] if trace_id else [], trace_bundles=trace_bundles)

    def export_trace(self, trace_id: str) -> ExportArtifacts:
        trace_id = str(trace_id).strip()
        if not trace_id:
            raise ValueError('trace_id is required')
        detail = self.result_store.get_result(trace_id)
        if detail is None:
            raise ValueError('trace_not_found')
        result_ids = self.result_store.result_ids_for_trace_ids([trace_id]) or [str(detail.get('id', trace_id))]
        trace_bundle = self.result_store.trace_bundle_for_result(result_ids[0] if result_ids else trace_id)
        return self._export_scope(scope='trace', scope_id=trace_id, items=[detail], result_ids=result_ids, trace_ids=[trace_id], trace_bundles={trace_id: trace_bundle})

    def _export_scope(self, *, scope: str, scope_id: str, items: list[dict[str, Any]], result_ids: list[str], trace_ids: list[str], trace_bundles: dict[str, dict[str, Any]]) -> ExportArtifacts:
        recipe_ids = sorted({str(item.get('recipeId', '')) for item in items if item.get('recipeId')})
        safe_scope_id = _safe_name(scope_id)
        staging_root = self.exports_root / '.staging' / f'{scope}-{safe_scope_id}-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
        if staging_root.exists():
            shutil.rmtree(staging_root)
        staging_root.mkdir(parents=True, exist_ok=True)

        trace_id_set = {trace_id for trace_id in trace_ids if trace_id}
        self._write_manifest(staging_root, scope=scope, scope_id=scope_id, items=items, result_ids=result_ids, trace_ids=trace_id_set, recipe_ids=recipe_ids)
        self._write_results_csv(staging_root / 'results.csv', items)
        self._write_json(staging_root / 'results.json', items)
        summary_batch_id = str(items[0].get('batchId', '')) if scope != 'batch' and items else scope_id
        self._write_json(staging_root / 'batch_summary.json', self.result_store.batch_summary(batch_id=summary_batch_id) if summary_batch_id else {'batchId': '', 'total': len(items)})
        self._write_filtered_jsonl(staging_root / 'cycle_summary.jsonl', self.log_root / 'results' / 'cycle_summary.jsonl', lambda row: str(row.get('trace_id', '')) in trace_id_set)
        self._write_filtered_jsonl(staging_root / 'events.jsonl', self.log_root / 'events' / 'event_log.jsonl', lambda row: self._event_matches(row, batch_id=summary_batch_id, trace_ids=trace_id_set))
        self._copy_trace_files(staging_root / 'traces', trace_id_set)
        self._copy_evidence(staging_root / 'artifacts', trace_bundles=trace_bundles, items=items)
        self._copy_recipe_snapshots(staging_root / 'recipe_snapshot', recipe_ids)

        export_path = self.exports_root / f'{scope}-{safe_scope_id}.zip'
        temp_zip = export_path.with_suffix('.zip.tmp')
        with ZipFile(temp_zip, 'w', compression=ZIP_DEFLATED) as zf:
            for path in sorted(staging_root.rglob('*')):
                if path.is_file():
                    zf.write(path, arcname=str(path.relative_to(staging_root)))
        temp_zip.replace(export_path)
        shutil.rmtree(staging_root, ignore_errors=True)
        return ExportArtifacts(export_path=export_path, item_count=len(items), trace_count=len(trace_id_set))

    def _write_manifest(self, root: Path, *, scope: str, scope_id: str, items: list[dict[str, Any]], result_ids: list[str], trace_ids: set[str], recipe_ids: list[str]) -> None:
        manifest = {
            'schemaVersion': '1.2',
            'generatedAt': utc_now(),
            'scope': scope,
            'scopeId': scope_id,
            'batchId': str(items[0].get('batchId', scope_id)) if items else scope_id,
            'itemCount': len(items),
            'traceCount': len(trace_ids),
            'resultIds': result_ids,
            'traceIds': sorted(trace_ids),
            'recipes': recipe_ids,
            'exportedFiles': [
                'manifest.json',
                'batch_summary.json',
                'results.csv',
                'results.json',
                'cycle_summary.jsonl',
                'events.jsonl',
                'recipe_snapshot/',
                'traces/',
                'artifacts/',
            ],
        }
        self._write_json(root / 'manifest.json', manifest)

    def _write_results_csv(self, path: Path, items: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        headers = [
            'id', 'timestamp', 'traceId', 'batchId', 'recipeId', 'recipeName', 'decision', 'category', 'defectType', 'qrText',
            'metricValue', 'metricLabel', 'cycleMs', 'imageUrl', 'overlayUrl', 'explanation',
        ]
        with path.open('w', encoding='utf-8', newline='') as fh:
            writer = csv.DictWriter(fh, fieldnames=headers)
            writer.writeheader()
            for item in items:
                writer.writerow({
                    'id': item.get('id', ''),
                    'timestamp': item.get('timestamp', ''),
                    'traceId': item.get('traceId', ''),
                    'batchId': item.get('batchId', ''),
                    'recipeId': item.get('recipeId', ''),
                    'recipeName': item.get('recipeName', ''),
                    'decision': item.get('decision', ''),
                    'category': item.get('category', ''),
                    'defectType': item.get('defectType', ''),
                    'qrText': item.get('qrText', ''),
                    'metricValue': item.get('metricValue', ''),
                    'metricLabel': item.get('metricLabel', ''),
                    'cycleMs': item.get('cycleMs', ''),
                    'imageUrl': item.get('imageUrl', ''),
                    'overlayUrl': item.get('overlayUrl', ''),
                    'explanation': ' | '.join(str(v) for v in item.get('explanation', []) or []),
                })

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

    def _write_filtered_jsonl(self, destination: Path, source: Path, predicate) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        rows: list[str] = []
        if source.exists():
            with source.open('r', encoding='utf-8') as fh:
                for line in fh:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        payload = json.loads(text)
                    except Exception:
                        continue
                    if isinstance(payload, dict) and predicate(payload):
                        rows.append(json.dumps(payload, ensure_ascii=False))
        destination.write_text('\n'.join(rows) + ('\n' if rows else ''), encoding='utf-8')

    def _copy_trace_files(self, destination: Path, trace_ids: Iterable[str]) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        traces_root = self.log_root / 'traces'
        for trace_id in sorted({trace_id for trace_id in trace_ids if trace_id}):
            source = traces_root / f'{trace_id}.jsonl'
            if source.exists():
                shutil.copy2(source, destination / source.name)

    def _copy_evidence(self, destination: Path, *, trace_bundles: dict[str, dict[str, Any]], items: Iterable[dict[str, Any]]) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        seen: set[tuple[str, str]] = set()
        grouped_fallback: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            trace_id = str(item.get('traceId', '') or item.get('id', 'unknown'))
            grouped_fallback.setdefault(trace_id, []).append(item)

        trace_sources = dict(trace_bundles)
        if not trace_sources:
            trace_sources = {trace_id: {'artifacts': []} for trace_id in grouped_fallback}

        for trace_id, bundle in sorted(trace_sources.items()):
            artifacts = bundle.get('artifacts', []) if isinstance(bundle.get('artifacts', []), list) else []
            if not artifacts:
                artifacts = []
                for item in grouped_fallback.get(trace_id, []):
                    for key, kind in (('imagePath', 'raw'), ('overlayPath', 'annotated')):
                        raw_path = str(item.get(key, '')).strip()
                        if raw_path:
                            artifacts.append({'path': raw_path, 'kind': kind})
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    continue
                raw_path = str(artifact.get('path', '')).strip()
                subdir = _safe_name(str(artifact.get('kind', 'artifact')) or 'artifact')
                if not raw_path:
                    continue
                try:
                    source = self._resolve_log_path(raw_path)
                except ValueError:
                    continue
                if not source.exists() or not source.is_file():
                    continue
                signature = (subdir, str(source.resolve()))
                if signature in seen:
                    continue
                seen.add(signature)
                target_dir = destination / subdir
                target_dir.mkdir(parents=True, exist_ok=True)
                target = target_dir / f'{_safe_name(trace_id)}-{source.name}'
                shutil.copy2(source, target)

    def _copy_recipe_snapshots(self, destination: Path, recipe_ids: Iterable[str]) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        active = self.recipe_store.current_default()
        if active:
            self._write_json(destination / 'active_recipe.json', active)
        for recipe_id in sorted({recipe_id for recipe_id in recipe_ids if recipe_id}):
            recipe = self.recipe_store.load_by_id(recipe_id)
            if recipe:
                self._write_json(destination / f'{_safe_name(recipe_id)}.json', recipe)

    def _resolve_log_path(self, raw_path: str) -> Path:
        return resolve_log_artifact_path(self.log_root, raw_path)

    def _event_matches(self, payload: dict[str, Any], *, batch_id: str, trace_ids: set[str]) -> bool:
        if batch_id and str(payload.get('batch_id', '')) == batch_id:
            return True
        if str(payload.get('trace_id', '')) in trace_ids:
            return True
        detail = payload.get('detail', {}) if isinstance(payload.get('detail', {}), dict) else {}
        if batch_id and str(detail.get('batch_id', '')) == batch_id:
            return True
        if str(detail.get('trace_id', '')) in trace_ids:
            return True
        return False
