from pathlib import Path
from types import SimpleNamespace

from inspection_hmi_gateway.telemetry_service import TelemetryService
from inspection_hmi_gateway.server.query_services import TelemetryGatewayQueryService


def test_telemetry_service_reads_bridge_config(tmp_path: Path, monkeypatch):
    config = tmp_path / 'telemetry.yaml'
    config.write_text('''bridges:\n  - id: foxglove\n    type: foxglove_bridge\n    enabled: true\n    url: ws://localhost:8765\n''', encoding='utf-8')
    svc = TelemetryService.__new__(TelemetryService); svc.config_path = config; svc.probe_timeout_sec = 0.1
    class _Sock:
        def __enter__(self): return self
        def __exit__(self, *args): return False
    monkeypatch.setattr('inspection_hmi_gateway.telemetry_service.socket.create_connection', lambda *args, **kwargs: _Sock())
    bridges = svc.list_bridges(); assert bridges[0]['id'] == 'foxglove'; assert bridges[0]['enabled'] is True; assert bridges[0]['reachable'] is True; assert bridges[0]['status'] == 'ONLINE'


def test_telemetry_query_service_falls_back_to_static_config(tmp_path: Path, monkeypatch) -> None:
    telemetry = tmp_path / 'telemetry.yaml'
    telemetry.write_text(
        '''bridges:\n  - id: rosbridge\n    type: rosbridge_websocket\n    enabled: false\n    url: ws://127.0.0.1:9090\n''',
        encoding='utf-8',
    )
    context = SimpleNamespace(log_root=tmp_path / 'runtime', telemetry_config_path=telemetry)
    context.log_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr('inspection_hmi_gateway.telemetry_service.socket.create_connection', lambda *args, **kwargs: (_ for _ in ()).throw(OSError('offline')))
    bridges = TelemetryGatewayQueryService(context).list_bridges()
    assert bridges[0]['id'] == 'rosbridge'
    assert bridges[0]['status'] == 'DISABLED'
