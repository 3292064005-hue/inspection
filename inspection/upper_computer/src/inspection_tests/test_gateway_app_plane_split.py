from pathlib import Path


def test_gateway_application_boundary_is_split_into_explicit_planes() -> None:
    root = Path(__file__).resolve().parents[2] / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway'
    application_planes = (root / 'application_planes.py').read_text(encoding='utf-8')
    application_service = (root / 'application_service.py').read_text(encoding='utf-8')
    gateway_runtime = (root / 'gateway_runtime.py').read_text(encoding='utf-8')
    assert 'class GatewayControlPlane' in application_planes
    assert 'class GatewayQueryPlane' in application_planes
    assert 'class GatewayProjectionPlane' in application_planes
    assert 'build_gateway_application_boundary' in application_planes
    assert 'GatewayApplicationService' in application_service
    assert 'build_gateway_application_boundary' in application_service
    assert 'self.control_plane = self.app.control_plane' in gateway_runtime
    assert 'self.query_plane = self.app.query_plane' in gateway_runtime
