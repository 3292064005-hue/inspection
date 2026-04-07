#!/usr/bin/env python3
"""ROS 2 Humble release gate preflight checks.

Centralizes environment validation for release-gate workflows so build/runtime
validation fails with one coherent preflight report instead of fragmented shell
errors.
"""
from __future__ import annotations
import argparse, json, os, pathlib, platform, shutil, subprocess, sys
from dataclasses import asdict, dataclass
from typing import List
@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str
@dataclass
class PreflightReport:
    workspaceRoot: str
    pythonVersion: str
    checks: List[CheckResult]
    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

def _read_os_release() -> dict[str, str]:
    data: dict[str, str] = {}
    os_release = pathlib.Path('/etc/os-release')
    if not os_release.exists():
        return data
    for line in os_release.read_text(encoding='utf-8').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            data[key] = value.strip().strip('"')
    return data

def _node_major() -> int | None:
    node = shutil.which('node')
    if not node:
        return None
    completed = subprocess.run([node, '--version'], check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        return None
    version_text = completed.stdout.strip() or completed.stderr.strip()
    if not version_text.startswith('v'):
        return None
    try:
        return int(version_text[1:].split('.', 1)[0])
    except ValueError:
        return None

def _check_ubuntu_2204() -> CheckResult:
    data = _read_os_release(); distro = data.get('ID', '').lower(); version = data.get('VERSION_ID', '')
    return CheckResult('ubuntu22_04', distro == 'ubuntu' and version == '22.04', f"detected ID={distro or 'unknown'} VERSION_ID={version or 'unknown'}; expected ubuntu 22.04")

def _check_python() -> CheckResult:
    major, minor = sys.version_info[:2]
    return CheckResult('python3_10_plus', major == 3 and minor >= 10, f'detected Python {platform.python_version()}; expected >= 3.10')

def _check_node() -> CheckResult:
    major = _node_major()
    return CheckResult('node_20_or_22_lts', major in {20, 22}, f"detected Node major={major if major is not None else 'missing'}; expected 20 or 22 LTS")

def _check_ros_setup() -> CheckResult:
    setup_path = pathlib.Path('/opt/ros/humble/setup.bash'); env_distro = os.environ.get('ROS_DISTRO', '')
    passed = setup_path.exists() and (not env_distro or env_distro == 'humble')
    detail = f"setup_exists={setup_path.exists()} ROS_DISTRO={env_distro or 'unset'}; expected /opt/ros/humble/setup.bash and ROS_DISTRO unset or humble"
    return CheckResult('ros2_humble_setup', passed, detail)

def _check_colcon() -> CheckResult:
    colcon = shutil.which('colcon')
    return CheckResult('colcon_available', bool(colcon), f"detected colcon={colcon or 'missing'}")

def _check_frontend_dist(workspace_root: pathlib.Path) -> CheckResult:
    dist_index = workspace_root / 'frontend' / 'dist' / 'index.html'
    return CheckResult('frontend_dist_ready', dist_index.is_file(), f'detected frontend dist={dist_index if dist_index.is_file() else "missing"}; expected built frontend/dist/index.html')

def _check_install_setup(workspace_root: pathlib.Path) -> CheckResult:
    install_setup = workspace_root / 'install' / 'setup.bash'
    return CheckResult('workspace_install_setup', install_setup.is_file(), f'detected install/setup.bash={install_setup if install_setup.is_file() else "missing"}')

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Validate ROS 2 Humble release gate preconditions.')
    p.add_argument('--workspace-root', required=True)
    p.add_argument('--require-colcon', action='store_true')
    p.add_argument('--require-frontend-dist', action='store_true')
    p.add_argument('--require-install-setup', action='store_true')
    p.add_argument('--write-json', default='')
    return p.parse_args()

def main() -> int:
    args = _parse_args(); workspace_root = pathlib.Path(args.workspace_root).resolve()
    checks: List[CheckResult] = [_check_ubuntu_2204(), _check_python(), _check_node(), _check_ros_setup()]
    if args.require_colcon: checks.append(_check_colcon())
    if args.require_frontend_dist: checks.append(_check_frontend_dist(workspace_root))
    if args.require_install_setup: checks.append(_check_install_setup(workspace_root))
    report = PreflightReport(workspaceRoot=str(workspace_root), pythonVersion=platform.python_version(), checks=checks)
    if args.write_json:
        out_path = pathlib.Path(args.write_json); out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps({'workspaceRoot': report.workspaceRoot, 'pythonVersion': report.pythonVersion, 'passed': report.passed, 'checks': [asdict(c) for c in checks]}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    failed = [c for c in checks if not c.passed]
    if failed:
        for check in failed: print(f"[preflight:FAIL] {check.name}: {check.detail}", file=sys.stderr)
        return 1
    for check in checks: print(f"[preflight:OK] {check.name}: {check.detail}")
    return 0
if __name__ == '__main__':
    raise SystemExit(main())
