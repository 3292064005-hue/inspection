from __future__ import annotations

import csv
import json
from pathlib import Path

from inspection_hmi_gateway.evidence_repository import TraceEvidenceRepository


def _fixture(root: Path) -> None:
    (root / 'results').mkdir(parents=True, exist_ok=True)
    (root / 'traces').mkdir(parents=True, exist_ok=True)
    (root / 'images').mkdir(parents=True, exist_ok=True)
    (root / 'images' / 'raw.png').write_bytes(b'raw')
    (root / 'images' / 'ann.png').write_bytes(b'ann')
    with (root / 'results' / 'result_log.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['time', 'trace_id', 'batch_id', 'item_id', 'recipe_id', 'category', 'defect_type', 'score', 'qr_ok', 'qr_text', 'orientation_ok', 'color_name', 'color_ratio', 'image_path', 'annotated_image_path', 'detail_json'])
        writer.writerow(['2026-03-31T08:00:00Z', 'trace-evi', 'BATCH-1', 1, 'recipe-a', 'COLOR', 'SHIFT', 0.8, True, 'QR-1', True, 'red', 0.9, 'images/raw.png', 'images/ann.png', json.dumps({'trace_id': 'trace-evi', 'evidence': {'raw_path': 'images/raw.png', 'annotated_path': 'images/ann.png'}}, ensure_ascii=False)])
    with (root / 'results' / 'cycle_summary.jsonl').open('w', encoding='utf-8') as handle:
        handle.write(json.dumps({'trace_id': 'trace-evi', 'decision': 'NG', 'image_paths': {'raw': 'images/raw.png', 'annotated': 'images/ann.png'}}, ensure_ascii=False) + '\n')
    with (root / 'results' / 'replay_manifest.jsonl').open('w', encoding='utf-8') as handle:
        handle.write(json.dumps({'trace_id': 'trace-evi', 'trace_path': str(root / 'traces' / 'trace-evi.jsonl'), 'summary': {'trace_id': 'trace-evi'}, 'run_artifacts': {'bag_recording': {'enabled': False}}, 'config_snapshot': {'recipe_path': 'config_snapshot/recipe.yaml'}, 'artifacts': [{'kind': 'raw', 'path': 'images/raw.png'}, {'kind': 'annotated', 'path': 'images/ann.png'}]}, ensure_ascii=False) + '\n')
    with (root / 'results' / 'artifact_index.jsonl').open('w', encoding='utf-8') as handle:
        handle.write(json.dumps({'trace_id': 'trace-evi', 'batch_id': 'BATCH-1', 'item_id': 1, 'kind': 'raw', 'path': 'images/raw.png'}, ensure_ascii=False) + '\n')
    (root / 'traces' / 'trace-evi.jsonl').write_text(json.dumps({'type': 'inspection_result', 'trace_id': 'trace-evi'}, ensure_ascii=False) + '\n', encoding='utf-8')


def test_trace_evidence_repository_reconstructs_bundle(tmp_path: Path) -> None:
    _fixture(tmp_path)
    repository = TraceEvidenceRepository(tmp_path)

    bundle = repository.trace_bundle('trace-evi')
    assert bundle['traceId'] == 'trace-evi'
    assert bundle['eventCount'] == 1
    assert bundle['traceUrl'].startswith('/artifacts/traces/')
    assert bundle['artifactCount'] == 2
    kinds = {artifact['kind'] for artifact in bundle['artifacts']}
    assert kinds == {'raw', 'annotated'}
    assert bundle['runArtifacts']['bag_recording']['enabled'] is False


def test_trace_evidence_repository_lists_artifact_only_trace_ids(tmp_path: Path) -> None:
    results_dir = tmp_path / 'results'
    traces_dir = tmp_path / 'traces'
    results_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / 'artifact_index.jsonl').write_text(
        json.dumps({'trace_id': 'trace-artifact-only', 'kind': 'raw', 'path': 'results/raw.png'}) + '\n',
        encoding='utf-8',
    )
    repo = TraceEvidenceRepository(tmp_path)
    assert repo.list_trace_ids() == ['trace-artifact-only']


def test_trace_evidence_repository_tolerates_non_numeric_item_id(tmp_path: Path) -> None:
    results_dir = tmp_path / 'results'
    traces_dir = tmp_path / 'traces'
    results_dir.mkdir(parents=True, exist_ok=True)
    traces_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / 'result_log.csv').write_text(
        'time,trace_id,batch_id,item_id,recipe_id,category,defect_type,score,qr_ok,qr_text,orientation_ok,color_name,color_ratio,image_path,annotated_image_path,detail_json\n'
        '2026-03-31T08:00:00Z,trace-bad-item,BATCH-X,not-a-number,recipe-a,COLOR,SHIFT,0.8,True,QR-1,True,red,0.9,images/raw.png,images/ann.png,{}\n',
        encoding='utf-8',
    )
    (results_dir / 'artifact_index.jsonl').write_text(
        json.dumps({'trace_id': 'trace-bad-item', 'batch_id': 'BATCH-X', 'item_id': 'oops', 'kind': 'raw', 'path': 'images/raw.png'}, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    repo = TraceEvidenceRepository(tmp_path)
    bundle = repo.trace_bundle('trace-bad-item')
    assert bundle['artifactCount'] >= 1
    assert any(artifact['itemId'] == -1 for artifact in bundle['artifacts'])


def test_trace_evidence_repository_trace_bundles_for_ids_batches_without_duplicates(tmp_path: Path) -> None:
    _fixture(tmp_path)
    repository = TraceEvidenceRepository(tmp_path)
    bundles = repository.trace_bundles_for_ids(['trace-evi', 'trace-evi', '', 'missing-trace'])
    assert sorted(bundles.keys()) == ['missing-trace', 'trace-evi']
    assert bundles['trace-evi']['artifactCount'] == 2
    assert bundles['missing-trace']['traceId'] == 'missing-trace'
    assert bundles['missing-trace']['artifactCount'] == 0
