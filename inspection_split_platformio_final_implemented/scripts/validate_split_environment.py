#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def _emit(name: str, ok: bool, detail: str) -> None:
    status = 'OK' if ok else 'FAIL'
    print(f'[{status}] {name}: {detail}')


def _ubuntu_version() -> str:
    os_release = Path('/etc/os-release')
    if not os_release.exists():
        return ''
    values: dict[str, str] = {}
    for line in os_release.read_text(encoding='utf-8').splitlines():
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key] = value.strip().strip('"')
    return values.get('VERSION_ID', '')


def _node_major() -> int | None:
    node_path = shutil.which('node')
    if not node_path:
        return None
    output = subprocess.check_output([node_path, '--version'], text=True).strip().lstrip('v')
    return int(output.split('.', 1)[0])


def main() -> int:
    parser = argparse.ArgumentParser(description='Validate split-delivery development/CI/release environment.')
    parser.add_argument('--workspace-root', default='.')
    parser.add_argument('--mode', choices=('dev', 'ci', 'release'), default='dev')
    parser.add_argument('--expect-ros', default='')
    parser.add_argument('--require-platformio', action='store_true')
    parser.add_argument('--require-colcon', action='store_true')
    parser.add_argument('--require-node', action='store_true')
    args = parser.parse_args()

    root = Path(args.workspace_root).resolve()
    failures = 0

    linux_ok = platform.system() == 'Linux'
    _emit('os', linux_ok, platform.system())
    if not linux_ok:
        failures += 1

    ubuntu = _ubuntu_version()
    ubuntu_ok = True if args.mode != 'release' else ubuntu == '22.04'
    _emit('ubuntu_release', ubuntu_ok, ubuntu or 'unknown')
    if not ubuntu_ok:
        failures += 1

    py_ok = sys.version_info >= (3, 10)
    _emit('python', py_ok, platform.python_version())
    if not py_ok:
        failures += 1

    node_major = _node_major()
    node_needed = args.require_node or args.mode in {'ci', 'release'}
    node_ok = (node_major in {20, 22}) if node_needed else True
    _emit('node', node_ok, str(node_major) if node_major is not None else 'missing')
    if node_needed and not node_ok:
        failures += 1

    colcon_path = shutil.which('colcon')
    colcon_needed = args.require_colcon or args.mode == 'release'
    colcon_ok = bool(colcon_path) if colcon_needed else True
    _emit('colcon', colcon_ok, colcon_path or 'missing')
    if colcon_needed and not colcon_ok:
        failures += 1

    pio_path = shutil.which('platformio') or shutil.which('pio')
    pio_needed = args.require_platformio or args.mode == 'release'
    pio_ok = bool(pio_path) if pio_needed else True
    _emit('platformio', pio_ok, pio_path or 'missing')
    if pio_needed and not pio_ok:
        failures += 1

    manifest = root / 'release' / 'split_release_manifest.yaml'
    version_manifest = root / 'release' / 'version_manifest.yaml'
    workflow = root / '.github' / 'workflows' / 'split_delivery_ci.yml'
    for name, path in [('upper_computer', root / 'upper_computer'), ('firmware', root / 'firmware'), ('release_manifest', manifest), ('version_manifest', version_manifest), ('split_workflow', workflow)]:
        ok = path.exists()
        _emit(name, ok, str(path))
        if not ok:
            failures += 1

    ros_env = os.environ.get('ROS_DISTRO', '')
    expect_ros = (args.expect_ros or ('humble' if args.mode == 'release' else '')).strip()
    ros_ok = True if not expect_ros else ros_env == expect_ros
    _emit('ros_distro', ros_ok, ros_env or 'unset')
    if not ros_ok:
        failures += 1

    return 0 if failures == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
