from __future__ import annotations
from pathlib import Path
import socket
from typing import Any
from urllib.parse import urlparse
import yaml
from inspection_utils.io_common import resolve_resource_path
class TelemetryService:
    def __init__(self, config_path: str = 'config/system/telemetry.yaml', *, probe_timeout_sec: float = 0.15) -> None:
        self.config_path = resolve_resource_path(config_path, package_name='inspection_hmi_gateway', start=__file__)
        self.probe_timeout_sec = max(0.05, float(probe_timeout_sec))
    def _probe_url(self, raw_url: str) -> dict[str, Any]:
        parsed = urlparse(str(raw_url or '').strip())
        if not parsed.scheme or not parsed.hostname or parsed.port is None:
            return {'reachable': False, 'status': 'UNCONFIGURED', 'probeError': 'invalid_url'}
        try:
            with socket.create_connection((parsed.hostname, int(parsed.port)), timeout=self.probe_timeout_sec):
                return {'reachable': True, 'status': 'ONLINE', 'probeError': ''}
        except OSError as exc:
            return {'reachable': False, 'status': 'OFFLINE', 'probeError': str(exc)}
    def list_bridges(self) -> list[dict[str, Any]]:
        path = Path(self.config_path)
        if not path.exists():
            return []
        payload = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        bridges = payload.get('bridges', []) if isinstance(payload, dict) else []
        result=[]
        for item in bridges:
            if not isinstance(item, dict):
                continue
            url = str(item.get('url', ''))
            probe = self._probe_url(url) if bool(item.get('enabled', False)) else {'reachable': False, 'status': 'DISABLED', 'probeError': ''}
            result.append({'id': str(item.get('id', '')), 'type': str(item.get('type', '')), 'enabled': bool(item.get('enabled', False)), 'url': url, 'topicPrefix': str(item.get('topicPrefix', '/inspection')), 'note': str(item.get('note', '')), **probe})
        return result
