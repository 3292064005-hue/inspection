from pathlib import Path


def test_gateway_service_modules_are_split_by_query_and_command() -> None:
    root = Path(__file__).resolve().parents[2]
    query = root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'query_services.py'
    command = root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'command_services.py'
    application_service = root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'application_service.py'
    compat = root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'services.py'
    assert query.exists()
    assert command.exists()
    assert application_service.exists()
    assert not compat.exists()
    assert 'GatewayApplicationService' in application_service.read_text(encoding='utf-8')


def test_gateway_routers_import_explicit_query_or_command_services() -> None:
    root = Path(__file__).resolve().parents[2]
    station = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'routers' / 'station.py').read_text(encoding='utf-8')
    actions = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'routers' / 'actions.py').read_text(encoding='utf-8')
    exports = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'routers' / 'exports.py').read_text(encoding='utf-8')
    assert 'StationQueryService' in station
    assert 'ActionQueryService' in actions and 'ActionCommandService' in actions
    assert 'ExportQueryService' in exports and 'ExportCommandService' in exports
