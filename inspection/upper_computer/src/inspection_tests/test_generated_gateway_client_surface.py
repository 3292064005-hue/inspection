from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_generated_gateway_client_keeps_frontend_required_read_operations() -> None:
    text = (ROOT / 'frontend' / 'src' / 'shared' / 'gateway' / 'generated' / 'actionApi.ts').read_text(encoding='utf-8')
    assert 'async getActionCatalog' in text
    assert 'async getActionCapabilityMatrix' in text
    assert 'async listActionJobs' in text
    assert 'async getActionJob' in text
    assert 'async cancelActionJob' in text
    assert 'async submitRunCalibrationAction' not in text
    assert 'async submitRunBenchmarkAction' not in text
    assert 'async runLegacyDiagnosticsAction' not in text
