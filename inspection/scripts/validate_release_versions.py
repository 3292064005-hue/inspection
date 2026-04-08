#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import yaml


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}


def _find_python_version(path: Path) -> str | None:
    match = re.search(r"version\s*=\s*['\"]([^'\"]+)['\"]", path.read_text(encoding='utf-8'))
    return match.group(1) if match else None


def _iter_package_xml_versions(src_root: Path) -> list[tuple[Path, str | None]]:
    pairs: list[tuple[Path, str | None]] = []
    for package_xml in src_root.glob('*/package.xml'):
        match = re.search(r'<version>([^<]+)</version>', package_xml.read_text(encoding='utf-8'))
        pairs.append((package_xml, match.group(1).strip() if match else None))
    return pairs


def _iter_setup_versions(src_root: Path) -> list[tuple[Path, str | None]]:
    pairs: list[tuple[Path, str | None]] = []
    for setup_py in src_root.glob('*/setup.py'):
        pairs.append((setup_py, _find_python_version(setup_py)))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate version/protocol consistency against release/version_manifest.yaml')
    parser.add_argument('--workspace-root', default='.')
    args = parser.parse_args()
    root = Path(args.workspace_root).resolve()

    version_manifest = _load_yaml(root / 'release' / 'version_manifest.yaml')
    split_manifest = _load_yaml(root / 'release' / 'split_release_manifest.yaml')
    errors: list[str] = []

    workspace_version = str(version_manifest['workspaceVersion'])
    protocol_version = str(version_manifest['protocolVersion'])
    stm32_fw = str(version_manifest['stm32StationFirmwareVersion'])
    esp32_fw = str(version_manifest['esp32CameraFirmwareVersion'])

    src_root = root / 'upper_computer' / 'src'
    for path, value in _iter_package_xml_versions(src_root):
        if value != workspace_version:
            errors.append(f'{path.relative_to(root)} version {value!r} != workspaceVersion {workspace_version!r}')
    for path, value in _iter_setup_versions(src_root):
        if value != workspace_version:
            errors.append(f'{path.relative_to(root)} version {value!r} != workspaceVersion {workspace_version!r}')

    stm32_header = (root / 'firmware' / 'stm32_station_platformio' / 'include' / 'inspection_station_config.h').read_text(encoding='utf-8')
    stm32_pio = (root / 'firmware' / 'stm32_station_platformio' / 'platformio.ini').read_text(encoding='utf-8')
    esp32_header = (root / 'firmware' / 'esp32s3_camera_platformio' / 'include' / 'inspection_camera_config.h').read_text(encoding='utf-8')
    esp32_pio = (root / 'firmware' / 'esp32s3_camera_platformio' / 'platformio.ini').read_text(encoding='utf-8')
    stm32_doc = (root / 'docs' / 'STM32_SERIAL_PROTOCOL.md').read_text(encoding='utf-8')
    esp32_doc = (root / 'docs' / 'ESP32S3_CAMERA_API.md').read_text(encoding='utf-8')

    for text, label, expected in [
        (stm32_header, 'STM32 header firmware version', stm32_fw),
        (stm32_pio, 'STM32 platformio firmware version', stm32_fw),
        (esp32_header, 'ESP32 header firmware version', esp32_fw),
        (esp32_pio, 'ESP32 platformio firmware version', esp32_fw),
        (stm32_doc, 'STM32 protocol doc firmware version', stm32_fw),
        (esp32_doc, 'ESP32 API doc firmware version', esp32_fw),
    ]:
        if expected not in text:
            errors.append(f'{label} missing expected string {expected!r}')

    if protocol_version not in stm32_header or protocol_version not in stm32_pio or protocol_version not in stm32_doc:
        errors.append(f'STM32 protocol version {protocol_version!r} not consistently declared')

    if str(split_manifest.get('protocolVersion')) != protocol_version:
        errors.append('split manifest protocolVersion mismatch')
    if str(split_manifest.get('generatedFrom', '')) != 'release/version_manifest.yaml':
        errors.append('split manifest generatedFrom mismatch')
    components = split_manifest.get('components', {})
    if str(components.get('upperComputerWorkspace', {}).get('version')) != workspace_version:
        errors.append('split manifest upperComputerWorkspace.version mismatch')
    if str(components.get('stm32StationFirmware', {}).get('firmwareVersion')) != stm32_fw:
        errors.append('split manifest stm32StationFirmware.firmwareVersion mismatch')
    if str(components.get('esp32CameraFirmware', {}).get('firmwareVersion')) != esp32_fw:
        errors.append('split manifest esp32CameraFirmware.firmwareVersion mismatch')

    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
