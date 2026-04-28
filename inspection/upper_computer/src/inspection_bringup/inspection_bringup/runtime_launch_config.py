from __future__ import annotations

from pathlib import Path
from typing import Any

from inspection_utils.config_common import build_effective_runtime_bundle
from inspection_utils.io_common import resolve_resource_path

_CAMERA_NODE_KEYS = {'camera_provider','camera_index','mock_mode','mock_color','frame_width','frame_height','hz','max_reconnect_attempts','reconnect_backoff_sec','stale_frame_threshold_ms','esp32_base_url','esp32_snapshot_path','esp32_health_path','esp32_request_timeout_ms','esp32_auth_header','esp32_auth_token'}
_STATION_BRIDGE_KEYS = {'adapter_name','protocol_version','supported_action_codes','station_capability_profile','serial_port','baudrate','position_delay_sec','sort_delay_sec','heartbeat_sec','ack_stale_timeout_sec','heartbeat_watchdog_sec','enable_startup_handshake'}
_FSM_KEYS = {'auto_start','feed_timeout_sec','position_timeout_sec','capture_frame_timeout_sec','capture_timeout_sec','analyze_timeout_sec','decision_timeout_sec','sort_ack_timeout_sec','sort_done_timeout_sec','sort_timeout_sec','recovery_timeout_sec','feed_retry_limit','capture_retry_limit','analyze_retry_limit','sort_retry_limit','auto_self_check_pass','auto_recovery_pass','allow_manual_mode'}

def _filter_parameters(source: dict[str, Any], allowed_keys: set[str]) -> dict[str, Any]:
    return {k: v for k, v in source.items() if k in allowed_keys}

def _path_string(path: Path) -> str:
    return path.as_posix()

def build_launch_runtime_payload(*, recipe_path: str, station_config_path: str, camera_config_path: str, profile_name: str, compatibility_path: str, package_name: str = 'inspection_bringup') -> dict[str, Any]:
    resolved_recipe_path = _path_string(resolve_resource_path(recipe_path, package_name=package_name, start=__file__))
    resolved_station_path = _path_string(resolve_resource_path(station_config_path, package_name=package_name, start=__file__))
    resolved_camera_path = _path_string(resolve_resource_path(camera_config_path, package_name=package_name, start=__file__))
    resolved_compatibility_path = _path_string(resolve_resource_path(compatibility_path, package_name=package_name, start=__file__))
    resolved_profile_path = _path_string(resolve_resource_path(str(Path('config/profiles') / f'{profile_name}.yaml'), package_name=package_name, start=__file__))
    effective = build_effective_runtime_bundle(recipe_path=resolved_recipe_path, camera_config_path=resolved_camera_path, station_config_path=resolved_station_path, profile_name=profile_name, profile_config_path=resolved_profile_path, compatibility_path=resolved_compatibility_path, resource_package_name=package_name, resource_start=__file__)
    return {'resolved_paths': {'recipe_path': resolved_recipe_path, 'station_config_path': resolved_station_path, 'camera_config_path': resolved_camera_path, 'compatibility_path': resolved_compatibility_path, 'profile_path': resolved_profile_path}, 'effective_bundle': effective, 'camera_parameters': _filter_parameters(effective['camera'], _CAMERA_NODE_KEYS), 'station_parameters': _filter_parameters(effective['station'], _STATION_BRIDGE_KEYS), 'fsm_parameters': _filter_parameters(effective['station'], _FSM_KEYS)}
