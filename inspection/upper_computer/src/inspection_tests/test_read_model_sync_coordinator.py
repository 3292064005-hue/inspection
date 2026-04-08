from __future__ import annotations

import json
from pathlib import Path

from inspection_hmi_gateway.read_model_policy import ReadModelPolicy
from inspection_hmi_gateway.read_model_sync_coordinator import build_readiness, resolve_projection_refresh_plan
from inspection_utils.read_model_store import ReadModelStore


def _prepare_runtime(root: Path) -> ReadModelStore:
    results = root / 'results'
    traces = root / 'traces'
    results.mkdir(parents=True, exist_ok=True)
    traces.mkdir(parents=True, exist_ok=True)
    (results / 'result_log.csv').write_text(
        'time,trace_id,batch_id,item_id,recipe_id,category,defect_type,score,qr_ok,qr_text,orientation_ok,color_name,color_ratio,image_path,annotated_image_path,detail_json\n',
        encoding='utf-8',
    )
    (results / 'cycle_summary.jsonl').write_text('', encoding='utf-8')
    (results / 'replay_manifest.jsonl').write_text('', encoding='utf-8')
    (results / 'artifact_index.jsonl').write_text('', encoding='utf-8')
    (traces / 'TRACE-1.jsonl').write_text(json.dumps({'type': 'capture_request', 'trace_id': 'TRACE-1'}) + '\n', encoding='utf-8')
    return ReadModelStore(root)


def test_read_model_sync_plan_requires_explicit_repair_in_legacy_mode(tmp_path: Path) -> None:
    store = _prepare_runtime(tmp_path / 'runtime')
    policy = ReadModelPolicy(mode='legacy', bootstrap_repair_on_empty_db=True, allow_runtime_repair_on_sync_mismatch=False, fallback_legacy_reads=False)
    plan = resolve_projection_refresh_plan(store, policy, projection_available=False)
    assert plan.action == 'require_explicit_repair'
    assert plan.reason == 'legacy_mode'


def test_read_model_readiness_marks_empty_projection_as_repair_required(tmp_path: Path) -> None:
    store = _prepare_runtime(tmp_path / 'runtime')
    readiness = build_readiness(store, ReadModelPolicy(), projection_available=False).as_dict()
    assert readiness['projectionAvailable'] is False
    assert readiness['repairRequired'] is True
