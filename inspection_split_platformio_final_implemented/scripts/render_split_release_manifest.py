#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import yaml


def build_manifest(version_payload: dict) -> dict:
    return {
        'schemaVersion': int(version_payload.get('schemaVersion', 1)),
        'releaseId': str(version_payload['releaseId']),
        'generatedFrom': 'release/version_manifest.yaml',
        'protocolVersion': str(version_payload['protocolVersion']),
        'components': {
            'upperComputerWorkspace': {
                'version': str(version_payload['workspaceVersion']),
                'path': 'upper_computer',
                'verificationWorkflow': '.github/workflows/split_delivery_ci.yml',
            },
            'stm32StationFirmware': {
                'firmwareVersion': str(version_payload['stm32StationFirmwareVersion']),
                'path': 'firmware/stm32_station_platformio',
                'platformioEnvironment': str(version_payload['platformioEnvironments']['stm32']),
            },
            'esp32CameraFirmware': {
                'firmwareVersion': str(version_payload['esp32CameraFirmwareVersion']),
                'path': 'firmware/esp32s3_camera_platformio',
                'platformioEnvironment': str(version_payload['platformioEnvironments']['esp32']),
            },
        },
        'compatibilityMatrix': [{
            'upperComputerWorkspaceVersion': str(version_payload['workspaceVersion']),
            'stm32StationFirmwareVersion': str(version_payload['stm32StationFirmwareVersion']),
            'esp32CameraFirmwareVersion': str(version_payload['esp32CameraFirmwareVersion']),
            'protocolVersion': str(version_payload['protocolVersion']),
            'status': 'supported',
        }],
        'notes': [
            'Top-level split-delivery CI validates upper-computer workspace, ROS2 Humble runtime, firmware compile gates, firmware contract tests, and protocol regressions.',
            'Rendered from release/version_manifest.yaml; do not hand-edit the generated manifest.',
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Render split release manifest from the version source of truth.')
    parser.add_argument('--workspace-root', default='.')
    parser.add_argument('--check', action='store_true', help='Fail if the checked-in manifest does not match the rendered output.')
    args = parser.parse_args()

    root = Path(args.workspace_root).resolve()
    version_manifest = root / 'release' / 'version_manifest.yaml'
    split_manifest = root / 'release' / 'split_release_manifest.yaml'
    version_payload = yaml.safe_load(version_manifest.read_text(encoding='utf-8')) or {}
    rendered = build_manifest(version_payload)
    rendered_text = yaml.safe_dump(rendered, allow_unicode=True, sort_keys=False)
    if args.check:
        existing = split_manifest.read_text(encoding='utf-8') if split_manifest.exists() else ''
        if existing != rendered_text:
            print('split release manifest is out of date; run scripts/render_split_release_manifest.py', file=sys.stderr)
            return 1
        return 0
    split_manifest.write_text(rendered_text, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
