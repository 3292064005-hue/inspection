from pathlib import Path


def test_gateway_service_modules_are_split_by_query_and_command() -> None:
    root = Path(__file__).resolve().parents[2]
    query = root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'query_services.py'
    command = root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'command_services.py'
    compat = root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'services.py'
    assert query.exists()
    assert command.exists()
    assert compat.exists()
    compat_text = compat.read_text(encoding='utf-8')
    assert 'Compatibility re-export layer' in compat_text
    assert 'StationService(StationQueryService, StationCommandService)' in compat_text


def test_gateway_routers_import_explicit_query_or_command_services() -> None:
    root = Path(__file__).resolve().parents[2]
    station = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'routers' / 'station.py').read_text(encoding='utf-8')
    actions = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'routers' / 'actions.py').read_text(encoding='utf-8')
    exports = (root / 'src' / 'inspection_hmi_gateway' / 'inspection_hmi_gateway' / 'server' / 'routers' / 'exports.py').read_text(encoding='utf-8')
    assert 'from ..query_services import StationQueryService' in station
    assert 'from ..command_services import StationCommandService' in station
    assert 'ActionQueryService' in actions and 'ActionCommandService' in actions
    assert 'ExportQueryService' in exports and 'ExportCommandService' in exports
