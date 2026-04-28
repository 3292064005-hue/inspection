from pathlib import Path


def test_compatibility_routes_are_fully_removed() -> None:
    root = Path(__file__).resolve().parents[2]
    router_support = root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'router_support.py'
    registry = root / 'config' / 'system' / 'compatibility_routes.yaml'
    text = router_support.read_text(encoding='utf-8')
    assert 'compatibility_routes_enabled' not in text
    assert 'compatibility_route_catalog' not in text
    registry_text = registry.read_text(encoding='utf-8')
    assert 'routes: {}' in registry_text
