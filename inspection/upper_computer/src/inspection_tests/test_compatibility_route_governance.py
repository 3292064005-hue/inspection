from pathlib import Path


def test_compatibility_route_governance_snapshot_is_empty() -> None:
    root = Path(__file__).resolve().parents[2]
    registry = root / 'config' / 'system' / 'compatibility_routes.yaml'
    registry_text = registry.read_text(encoding='utf-8')
    assert registry_text.strip() == 'routes: {}'


def test_no_runtime_documentation_mentions_compatibility_route_toggles() -> None:
    root = Path(__file__).resolve().parents[2]
    documents = [
        root / 'README.md',
        root / 'frontend' / 'README.md',
        root / 'docs' / 'ARCHITECTURE.md',
    ]
    legacy_tokens = (
        '_'.join(['INSPECTION', 'ENABLE', 'COMPATIBILITY', 'ROUTES']),
        '_'.join(['INSPECTION', 'COMPATIBILITY', 'ROUTE', 'STATION', 'ACTIONS', 'ENABLED']),
        '_'.join(['INSPECTION', 'COMPATIBILITY', 'ROUTE', 'DIAGNOSTICS', 'ACTIONS', 'ENABLED']),
        ' '.join(['compatibility', 'routes', 'can', 'be', 're-enabled']),
    )
    for document in documents:
        text = document.read_text(encoding='utf-8')
        for token in legacy_tokens:
            assert token not in text, f'{token} leaked in {document}'
