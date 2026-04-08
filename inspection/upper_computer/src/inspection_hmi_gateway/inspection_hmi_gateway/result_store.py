from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from inspection_utils.logging_tools import safe_json_loads
from inspection_utils.paths import resolve_runtime_path
from inspection_utils.read_model_projection import safe_float, safe_int

from .evidence_repository import TraceEvidenceRepository
from .read_model_maintenance import ReadModelMaintenanceCoordinator
from .read_model_policy import ReadModelPolicy, load_read_model_policy
from .read_model_repository import ReadModelRepository, ReadModelSyncRequiredError


class ResultStore:
    """Query facade for inspection results.

    The store treats the SQLite projection as the canonical query surface. Legacy
    CSV/file scans remain available only when the active policy explicitly opts
    into degraded fallback mode.
    """

    def __init__(self, log_root: str | Path = 'logs/runtime', *, read_model_policy: ReadModelPolicy | None = None) -> None:
        self.log_root = resolve_runtime_path(log_root, start=__file__)
        self.results_root = self.log_root / 'results'
        self.result_csv = self.results_root / 'result_log.csv'
        self.trace_repository = TraceEvidenceRepository(self.log_root)
        self.read_model_policy = read_model_policy or load_read_model_policy()
        self.read_model_repository = ReadModelRepository(self.log_root, policy=self.read_model_policy)
        self.maintenance = ReadModelMaintenanceCoordinator(log_root=self.log_root, repository=self.read_model_repository, policy=self.read_model_policy)
        self._legacy_records: list[dict[str, Any]] = []
        self._read_model_status: dict[str, Any] = {
            'mode': 'COLD',
            'degraded': False,
            'lastError': '',
            'repairRequired': False,
            'projectionAvailable': False,
            'fallbackEnabled': bool(self.read_model_policy.fallback_legacy_reads),
            'querySurface': 'projection',
        }
        try:
            self.maintenance.bootstrap_if_needed()
        except Exception as exc:  # pragma: no cover - defensive bootstrap status path
            readiness = self.read_model_repository.readiness()
            self._set_read_model_status(
                mode='PROJECTION_ERROR',
                degraded=True,
                last_error=str(exc),
                repair_required=bool(readiness.get('repairRequired')),
                projection_available=bool(readiness.get('projectionAvailable')),
                query_surface='projection',
            )

    def _set_read_model_status(
        self,
        *,
        mode: str,
        degraded: bool,
        last_error: str = '',
        repair_required: bool = False,
        projection_available: bool = False,
        query_surface: str = 'projection',
    ) -> None:
        readiness = self.read_model_repository.readiness()
        maintenance = self.maintenance.status(readiness=readiness)
        self._read_model_status = {
            'mode': mode,
            'degraded': bool(degraded),
            'lastError': last_error,
            'repairRequired': bool(repair_required),
            'projectionAvailable': bool(projection_available),
            'fallbackEnabled': bool(self.read_model_policy.fallback_legacy_reads),
            'querySurface': str(query_surface),
            'maintenanceState': str(maintenance.get('maintenanceState', 'IDLE')),
            'repairRunning': bool(maintenance.get('repairRunning', False)),
            'lastRepairAt': str(maintenance.get('lastRepairAt', '')),
            'lastRepairReason': str(maintenance.get('lastReason', '')),
            'sourceSyncToken': str(maintenance.get('sourceSyncToken', readiness.get('sourceSyncToken', ''))),
            'materializedSyncToken': str(maintenance.get('materializedSyncToken', readiness.get('materializedSyncToken', ''))),
        }

    def read_model_status(self, *, refresh: bool = True) -> dict[str, Any]:
        """Return the current projection health/status payload.

        Args:
            refresh: Whether to refresh projection readiness before returning.

        Returns:
            A JSON-serializable projection status payload.

        Raises:
            No exception is intentionally raised.

        Boundary behavior:
            When status refresh fails the last observed status is returned with a
            degraded/error marker instead of re-raising.
        """
        if refresh:
            try:
                self._refresh_if_needed()
            except Exception as exc:  # pragma: no cover - defensive status path
                readiness = self.read_model_repository.readiness()
                self._set_read_model_status(
                    mode='PROJECTION_ERROR',
                    degraded=True,
                    last_error=str(exc),
                    repair_required=bool(readiness.get('repairRequired')),
                    projection_available=bool(readiness.get('projectionAvailable')),
                    query_surface='projection',
                )
        return dict(self._read_model_status)

    def _attach_read_model_status(self, record: dict[str, Any]) -> dict[str, Any]:
        enriched = dict(record)
        enriched['readModelStatus'] = dict(self._read_model_status)
        return enriched

    def _build_records(self) -> list[dict[str, Any]]:
        if not self.result_csv.exists():
            return []
        with self.result_csv.open('r', encoding='utf-8', newline='') as handle:
            raw_rows = list(csv.DictReader(handle))

        trace_ids = [str(row.get('trace_id', '')) for row in raw_rows if str(row.get('trace_id', ''))]
        trace_bundles = self.trace_repository.trace_bundles_for_ids(trace_ids) if trace_ids else {}
        rows: list[dict[str, Any]] = []
        for row in raw_rows:
            detail = safe_json_loads(row.get('detail_json', '') or '{}')
            trace_id = str(row.get('trace_id', ''))
            trace_bundle = trace_bundles.get(trace_id, {}) if trace_id else {}
            try:
                metric_value = float(row.get('score', ''))
            except (TypeError, ValueError):
                metric_value = None
            processing_ms = safe_float(detail.get('processing_ms', 0.0), default=0.0)
            rows.append(
                {
                    'id': trace_id or str(row.get('result_id', '')),
                    'resultId': trace_id or str(row.get('result_id', '')),
                    'timestamp': str(row.get('time', '')),
                    'traceId': trace_id,
                    'batchId': str(row.get('batch_id', '')),
                    'itemId': safe_int(str(row.get('item_id', '-1')).strip() or -1, default=-1),
                    'recipeId': str(row.get('recipe_id', '')),
                    'decision': str(detail.get('decision', row.get('decision', 'RECHECK'))),
                    'category': str(row.get('category', '')),
                    'defectType': str(row.get('defect_type', '')),
                    'qrText': str(row.get('qr_text', '')),
                    'metricValue': metric_value,
                    'metricLabel': 'score' if metric_value is not None else '',
                    'cycleMs': processing_ms,
                    'imagePath': str(row.get('image_path', '')),
                    'overlayPath': str(row.get('annotated_image_path', '')),
                    'traceUrl': str(trace_bundle.get('traceUrl', '')),
                    'artifactCount': safe_int(trace_bundle.get('artifactCount', 0), default=0),
                    'runArtifacts': trace_bundle.get('runArtifacts', {}),
                    'configSnapshot': trace_bundle.get('configSnapshot', {}),
                    'artifacts': trace_bundle.get('artifacts', []),
                    'traceSummary': trace_bundle.get('summary', {}),
                    'explanation': [item for item in [str(row.get('defect_type', '')), str(row.get('category', ''))] if item] or ['规则检测完成'],
                    'breakdown': {'analyzeMs': processing_ms, 'totalMs': processing_ms},
                }
            )
        rows.sort(key=lambda item: item.get('timestamp', ''), reverse=True)
        return rows

    def _run_projection_refresh(self) -> None:
        self.read_model_repository.refresh_if_needed()
        readiness = self.read_model_repository.readiness()
        self._set_read_model_status(
            mode='HOT',
            degraded=False,
            repair_required=bool(readiness.get('repairRequired')),
            projection_available=bool(readiness.get('projectionAvailable')),
            query_surface='projection',
        )

    def _run_legacy_fallback(self, *, mode: str, exc: Exception) -> None:
        readiness = self.read_model_repository.readiness()
        self._legacy_records = self._build_records()
        self._set_read_model_status(
            mode=mode,
            degraded=True,
            last_error=str(exc),
            repair_required=bool(readiness.get('repairRequired')),
            projection_available=bool(readiness.get('projectionAvailable')),
            query_surface='legacy_file_scan',
        )

    def _refresh_if_needed(self) -> None:
        try:
            self._run_projection_refresh()
            return
        except ReadModelSyncRequiredError as exc:
            if not self.read_model_policy.fallback_legacy_reads:
                readiness = self.read_model_repository.readiness()
                self._set_read_model_status(
                    mode='REPAIR_REQUIRED',
                    degraded=True,
                    last_error=str(exc),
                    repair_required=True,
                    projection_available=bool(readiness.get('projectionAvailable')),
                    query_surface='projection',
                )
                raise
            self._run_legacy_fallback(mode='REPAIR_REQUIRED', exc=exc)
        except Exception as exc:
            if not self.read_model_policy.fallback_legacy_reads:
                readiness = self.read_model_repository.readiness()
                self._set_read_model_status(
                    mode='PROJECTION_ERROR',
                    degraded=True,
                    last_error=str(exc),
                    repair_required=bool(readiness.get('repairRequired')),
                    projection_available=bool(readiness.get('projectionAvailable')),
                    query_surface='projection',
                )
                raise
            self._run_legacy_fallback(mode='FALLBACK_FILE_SCAN', exc=exc)

    def repair_read_model(self) -> None:
        self.maintenance.repair(reason='explicit_repair')
        self._refresh_if_needed()

    def _query_surface(self) -> str:
        return str(self._read_model_status.get('querySurface', 'projection'))

    def list_results(self) -> list[dict[str, Any]]:
        self._refresh_if_needed()
        if self._query_surface() == 'legacy_file_scan':
            return [self._attach_read_model_status(dict(item)) for item in self._legacy_records]
        rows = self.read_model_repository.list_results()
        return [self._attach_read_model_status(dict(item)) for item in rows]

    def get_result(self, result_id: str) -> dict[str, Any] | None:
        """Return one result detail from the materialized read model only.

        Args:
            result_id: Business result identifier or trace identifier.

        Returns:
            The normalized result payload, or ``None`` when the projection has no
            matching row.

        Raises:
            ReadModelSyncRequiredError: When the SQLite projection is stale or
                otherwise requires explicit repair before result details may be
                served.
            Exception: Any unexpected projection refresh error from the
                underlying repository.

        Boundary behavior:
            The detail path is projection-only. It never serves legacy file-scan
            payloads and never serves stale materialized rows while the read
            model reports ``repairRequired``. Callers must trigger explicit
            repair first, then retry the query.
        """
        self._refresh_if_needed()
        try:
            detail = self.read_model_repository.get_result(result_id)
        except ReadModelSyncRequiredError:
            readiness = self.read_model_repository.live_readiness()
            self._set_read_model_status(
                mode='REPAIR_REQUIRED',
                degraded=True,
                last_error='SQLite read model is stale; explicit repair is required before serving result details',
                repair_required=bool(readiness.get('repairRequired')),
                projection_available=bool(readiness.get('projectionAvailable')),
                query_surface='projection',
            )
            raise
        readiness = self.read_model_repository.live_readiness()
        if detail is None:
            return None
        self._set_read_model_status(
            mode='HOT',
            degraded=False,
            repair_required=False,
            projection_available=bool(readiness.get('projectionAvailable')),
            query_surface='projection',
        )
        return self._attach_read_model_status(detail)

    def query_results(self, **filters: Any) -> list[dict[str, Any]]:
        filtered, _ = self.query_result_page(**filters)
        return filtered

    def _legacy_matches(self, item: dict[str, Any], *, batch_id: str, recipe_id: str, decision: str, defect_type: str, qr_text: str, from_ts: str, to_ts: str) -> bool:
        if batch_id and str(item.get('batchId', '')) != str(batch_id):
            return False
        if recipe_id and str(item.get('recipeId', '')) != str(recipe_id):
            return False
        if decision and str(item.get('decision', '')) != str(decision):
            return False
        if defect_type and str(item.get('defectType', '')) != str(defect_type):
            return False
        if qr_text and qr_text not in str(item.get('qrText', '')):
            return False
        timestamp = str(item.get('timestamp', ''))
        if from_ts and timestamp and timestamp < str(from_ts):
            return False
        if to_ts and timestamp and timestamp > str(to_ts):
            return False
        return True

    def query_result_page(self, *, batch_id: str = '', recipe_id: str = '', decision: str = '', defect_type: str = '', qr_text: str = '', from_ts: str = '', to_ts: str = '', limit: int | None = None, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        self._refresh_if_needed()
        if self._query_surface() == 'legacy_file_scan':
            filtered = [
                dict(item)
                for item in self._legacy_records
                if self._legacy_matches(
                    item,
                    batch_id=batch_id,
                    recipe_id=recipe_id,
                    decision=decision,
                    defect_type=defect_type,
                    qr_text=qr_text,
                    from_ts=from_ts,
                    to_ts=to_ts,
                )
            ]
            total = len(filtered)
            if offset:
                filtered = filtered[offset:]
            if limit is not None:
                filtered = filtered[:limit]
            return [self._attach_read_model_status(dict(row)) for row in filtered], total
        rows, total = self.read_model_repository.query_result_page(batch_id=batch_id, recipe_id=recipe_id, decision=decision, defect_type=defect_type, qr_text=qr_text, from_ts=from_ts, to_ts=to_ts, limit=limit, offset=offset)
        readiness = self.read_model_repository.readiness()
        self._set_read_model_status(
            mode='HOT',
            degraded=False,
            repair_required=bool(readiness.get('repairRequired')),
            projection_available=bool(readiness.get('projectionAvailable')),
            query_surface='projection',
        )
        return [self._attach_read_model_status(dict(row)) for row in rows], total

    def result_ids_for_batch(self, batch_id: str) -> list[str]:
        self._refresh_if_needed()
        if self._query_surface() == 'legacy_file_scan':
            return [str(item.get('resultId', item.get('id', ''))) for item in self._legacy_records if str(item.get('batchId', '')) == str(batch_id)]
        return self.read_model_repository.result_ids_for_batch(batch_id)

    def trace_bundles_for_batch(self, batch_id: str) -> dict[str, dict[str, Any]]:
        self._refresh_if_needed()
        if self._query_surface() == 'legacy_file_scan':
            trace_ids = [str(item.get('traceId', '')) for item in self._legacy_records if str(item.get('batchId', '')) == str(batch_id)]
            return self.trace_repository.trace_bundles_for_ids(trace_ids)
        return self.read_model_repository.trace_bundles_for_batch(batch_id)

    def result_ids_for_trace_ids(self, trace_ids: list[str]) -> list[str]:
        self._refresh_if_needed()
        if self._query_surface() == 'legacy_file_scan':
            normalized = {str(trace_id) for trace_id in trace_ids if str(trace_id)}
            return [str(item.get('resultId', item.get('id', ''))) for item in self._legacy_records if str(item.get('traceId', '')) in normalized]
        return self.read_model_repository.result_ids_for_trace_ids(trace_ids)

    def trace_bundle_for_result(self, result_id: str) -> dict[str, Any]:
        self._refresh_if_needed()
        if self._query_surface() == 'legacy_file_scan':
            trace_id = next(
                (
                    str(item.get('traceId', ''))
                    for item in self._legacy_records
                    if item.get('id') == result_id or item.get('resultId') == result_id or item.get('traceId') == result_id
                ),
                '',
            )
            return self.trace_repository.trace_bundle(trace_id) if trace_id else {}
        trace_id = self.read_model_repository.trace_id_for_result(result_id)
        if not trace_id:
            return {}
        return self.read_model_repository.trace_bundle(trace_id)

    def artifact_records_for_result_ids(self, result_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        self._refresh_if_needed()
        if self._query_surface() == 'legacy_file_scan':
            mapping: dict[str, list[dict[str, Any]]] = {}
            for result_id in result_ids:
                bundle = self.trace_bundle_for_result(result_id)
                mapping[str(result_id)] = list(bundle.get('artifacts', [])) if isinstance(bundle, dict) else []
            return mapping
        return self.read_model_repository.artifact_records_for_result_ids(result_ids)

    def batch_summary(self, *, batch_id: str) -> dict[str, Any]:
        self._refresh_if_needed()
        if self._query_surface() == 'legacy_file_scan':
            rows = [item for item in self._legacy_records if str(item.get('batchId', '')) == str(batch_id)]
            total = len(rows)
            ok_count = sum(1 for item in rows if str(item.get('decision', '')) == 'OK')
            ng_count = sum(1 for item in rows if str(item.get('decision', '')) == 'NG')
            recheck_count = sum(1 for item in rows if str(item.get('decision', '')) == 'RECHECK')
            avg_cycle_ms = round(sum(float(item.get('cycleMs', 0.0) or 0.0) for item in rows) / total, 3) if total else 0.0
            return {
                'batchId': batch_id,
                'total': total,
                'ok': ok_count,
                'ng': ng_count,
                'recheck': recheck_count,
                'okCount': ok_count,
                'ngCount': ng_count,
                'recheckCount': recheck_count,
                'avgCycleMs': avg_cycle_ms,
                'yieldRate': round(ok_count / total, 4) if total else 0.0,
            }
        summary = self.read_model_repository.batch_summary(batch_id=batch_id)
        total = int(summary.get('total', 0) or 0)
        ok_count = int(summary.get('okCount', 0) or 0)
        ng_count = int(summary.get('ngCount', 0) or 0)
        recheck_count = int(summary.get('recheckCount', 0) or 0)
        yield_rate = ok_count / total if total > 0 else 0.0
        summary.setdefault('ok', ok_count)
        summary.setdefault('ng', ng_count)
        summary.setdefault('recheck', recheck_count)
        summary.setdefault('yieldRate', round(yield_rate, 4))
        return summary
