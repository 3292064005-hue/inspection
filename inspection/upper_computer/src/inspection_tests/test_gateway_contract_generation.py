from __future__ import annotations

import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from sync_gateway_contracts import sync  # noqa: E402


def test_gateway_contract_artifacts_are_generated_from_openapi() -> None:
    openapi_path = ROOT / 'frontend' / 'openapi' / 'inspection_gateway_openapi.json'
    ts_path = ROOT / 'frontend' / 'src' / 'shared' / 'gateway' / 'generated' / 'actionApi.ts'
    assert openapi_path.exists()
    assert ts_path.exists()
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        generated_openapi, generated_ts, _generated_public_ts = sync(tmp_root / 'inspection_gateway_openapi.json', tmp_root / 'actionApi.ts', tmp_root / 'gatewayApi.ts')
    assert openapi_path.read_text(encoding='utf-8') == generated_openapi
    assert ts_path.read_text(encoding='utf-8') == generated_ts
    assert 'submitStartBatchAction' in generated_ts
    assert 'StartBatchRequest' in generated_ts
    assert 'submitRunCalibrationAction' not in generated_ts
    assert 'submitRunBenchmarkAction' not in generated_ts
    assert 'getActionCatalog' in generated_ts
    assert 'getActionCapabilityMatrix' in generated_ts
    assert 'listActionJobs' in generated_ts


def test_internal_benchmark_route_is_not_in_public_openapi() -> None:
    import json
    openapi_path = ROOT / 'frontend' / 'openapi' / 'inspection_gateway_openapi.json'
    payload = json.loads(openapi_path.read_text(encoding='utf-8'))
    assert '/api/v1/actions/run-benchmark' not in payload.get('paths', {})
    assert '/api/internal/actions/run-benchmark' not in payload.get('paths', {})

