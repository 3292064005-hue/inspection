from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from inspection_utils.config_common import load_yaml
from inspection_utils.io_common import resolve_resource_path

READ_MODEL_MODE_HOT = 'hot'
READ_MODEL_MODE_REPAIR = 'repair'
READ_MODEL_MODE_LEGACY = 'legacy'
READ_MODEL_QUERY_REFRESH_DISABLED = 'disabled'
READ_MODEL_QUERY_REFRESH_TRACE_STREAM = 'trace_stream'
DEFAULT_POLICY_PATH = 'config/system/read_model.yaml'


class ReadModelPolicyError(RuntimeError): pass


@dataclass(frozen=True, slots=True)
class ReadModelPolicy:
    mode: str = READ_MODEL_MODE_HOT
    bootstrap_repair_on_empty_db: bool = True
    allow_runtime_repair_on_sync_mismatch: bool = False
    fallback_legacy_reads: bool = False
    query_side_trace_refresh: str = READ_MODEL_QUERY_REFRESH_DISABLED
    def normalized_mode(self) -> str: return normalize_read_model_mode(self.mode)
    def normalized_query_side_trace_refresh(self) -> str: return normalize_query_side_trace_refresh(self.query_side_trace_refresh)

def _as_bool(value, *, default: bool) -> bool:
    if value is None: return default
    if isinstance(value, bool): return value
    if isinstance(value, (int, float)): return bool(value)
    return str(value).strip().lower() in {'1','true','yes','on'}

def normalize_read_model_mode(raw: str | None) -> str:
    normalized = str(raw or READ_MODEL_MODE_HOT).strip().lower() or READ_MODEL_MODE_HOT
    if normalized not in {READ_MODEL_MODE_HOT, READ_MODEL_MODE_REPAIR, READ_MODEL_MODE_LEGACY}: raise ReadModelPolicyError(f'Unsupported read-model mode: {raw}')
    return normalized

def normalize_query_side_trace_refresh(raw: str | None) -> str:
    normalized = str(raw or READ_MODEL_QUERY_REFRESH_DISABLED).strip().lower() or READ_MODEL_QUERY_REFRESH_DISABLED
    if normalized not in {READ_MODEL_QUERY_REFRESH_DISABLED, READ_MODEL_QUERY_REFRESH_TRACE_STREAM}: raise ReadModelPolicyError(f'Unsupported query-side trace refresh mode: {raw}')
    return normalized

def load_read_model_policy(config_path: str | Path = DEFAULT_POLICY_PATH) -> ReadModelPolicy:
    resolved = resolve_resource_path(str(config_path), package_name='inspection_hmi_gateway', start=__file__)
    payload = load_yaml(resolved) if resolved.exists() else {}
    section = payload.get('read_model', {}) if isinstance(payload, dict) else {}
    if section and not isinstance(section, dict): raise ReadModelPolicyError('read_model policy section must be a mapping')
    mode = normalize_read_model_mode(os.environ.get('INSPECTION_READ_MODEL_MODE', section.get('mode', READ_MODEL_MODE_HOT)))
    query_side_trace_refresh = normalize_query_side_trace_refresh(os.environ.get('INSPECTION_READ_MODEL_QUERY_REFRESH', section.get('query_side_trace_refresh', READ_MODEL_QUERY_REFRESH_DISABLED)))
    fallback_legacy_reads = _as_bool(os.environ.get('INSPECTION_READ_MODEL_FALLBACK_LEGACY_READS', section.get('fallback_legacy_reads')), default=False)
    if fallback_legacy_reads: raise ReadModelPolicyError('Online legacy read fallback has been removed; use the explicit read-model repair path instead')
    return ReadModelPolicy(mode=mode, bootstrap_repair_on_empty_db=_as_bool(os.environ.get('INSPECTION_READ_MODEL_BOOTSTRAP_REPAIR_ON_EMPTY_DB', section.get('bootstrap_repair_on_empty_db')), default=True), allow_runtime_repair_on_sync_mismatch=_as_bool(os.environ.get('INSPECTION_READ_MODEL_ALLOW_RUNTIME_REPAIR', section.get('allow_runtime_repair_on_sync_mismatch')), default=False), fallback_legacy_reads=False, query_side_trace_refresh=query_side_trace_refresh)
