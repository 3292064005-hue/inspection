#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def _emit(name: str, status: str, detail: str) -> None:
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

    linux_needed = args.mode in {'ci', 'release'}
    linux_ok = platform.system() == 'Linux'
    os_status = 'PASS' if linux_ok else ('FAIL' if linux_needed else 'SKIP')
    _emit('os', os_status, platform.system())
    if linux_needed and not linux_ok:
        failures += 1

    ubuntu = _ubuntu_version()
    ubuntu_needed = args.mode == 'release'
    ubuntu_ok = ubuntu == '22.04' if ubuntu_needed else True
    ubuntu_status = 'PASS' if ubuntu_ok and ubuntu_needed else ('SKIP' if not ubuntu_needed else 'FAIL')
    _emit('ubuntu_release', ubuntu_status, ubuntu or 'unknown')
    if ubuntu_needed and not ubuntu_ok:
        failures += 1

    py_ok = sys.version_info >= (3, 10)
    _emit('python', 'PASS' if py_ok else 'FAIL', platform.python_version())
    if not py_ok:
        failures += 1

    node_needed = args.require_node or args.mode in {'ci', 'release'}
    node_major = _node_major() if node_needed else None
    node_ok = (node_major in {20, 22}) if node_needed else True
    node_status = 'PASS' if node_ok and node_needed else ('SKIP' if not node_needed else 'FAIL')
    _emit('node', node_status, str(node_major) if node_major is not None else 'missing')
    if node_needed and not node_ok:
        failures += 1

    colcon_path = shutil.which('colcon')
    colcon_needed = args.require_colcon or args.mode == 'release'
    colcon_ok = bool(colcon_path) if colcon_needed else True
    colcon_status = 'PASS' if colcon_ok and colcon_needed else ('SKIP' if not colcon_needed else 'FAIL')
    _emit('colcon', colcon_status, colcon_path or 'missing')
    if colcon_needed and not colcon_ok:
        failures += 1

    pio_path = shutil.which('platformio') or shutil.which('pio')
    pio_needed = args.require_platformio or args.mode == 'release'
    pio_ok = bool(pio_path) if pio_needed else True
    pio_status = 'PASS' if pio_ok and pio_needed else ('SKIP' if not pio_needed else 'FAIL')
    _emit('platformio', pio_status, pio_path or 'missing')
    if pio_needed and not pio_ok:
        failures += 1

    manifest = root / 'release' / 'split_release_manifest.yaml'
    version_manifest = root / 'release' / 'version_manifest.yaml'
    runtime_matrix = root / 'release' / 'runtime_validation_matrix.yaml'
    split_deployment = root / 'docs' / 'SPLIT_DEPLOYMENT.md'
    upper_architecture = root / 'upper_computer' / 'docs' / 'ARCHITECTURE.md'
    workflow = root / '.github' / 'workflows' / 'split_delivery_ci.yml'
    for name, path in [('upper_computer', root / 'upper_computer'), ('firmware', root / 'firmware'), ('release_manifest', manifest), ('version_manifest', version_manifest), ('runtime_validation_matrix', runtime_matrix), ('split_deployment', split_deployment), ('upper_architecture', upper_architecture), ('split_workflow', workflow)]:
        ok = path.exists()
        _emit(name, 'PASS' if ok else 'FAIL', str(path))
        if not ok:
            failures += 1

    ros_env = os.environ.get('ROS_DISTRO', '')
    expect_ros = (args.expect_ros or ('humble' if args.mode == 'release' else '')).strip()
    ros_needed = bool(expect_ros)
    ros_ok = True if not ros_needed else ros_env == expect_ros
    ros_status = 'PASS' if ros_ok and ros_needed else ('SKIP' if not ros_needed else 'FAIL')
    _emit('ros_distro', ros_status, ros_env or 'unset')
    if ros_needed and not ros_ok:
        failures += 1

    return 0 if failures == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
