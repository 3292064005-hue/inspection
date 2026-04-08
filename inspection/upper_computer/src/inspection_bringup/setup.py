from __future__ import annotations

from pathlib import Path
from setuptools import find_packages, setup

package_name = 'inspection_bringup'
ROOT = Path(__file__).resolve().parent
WORKSPACE_ROOT = ROOT.parent.parent


def collect_files(relative_root: str, *, anchor: Path | None = None) -> list[tuple[str, list[str]]]:
    source_root = anchor or ROOT
    root = source_root / relative_root
    if not root.exists():
        return []
    collected: dict[str, list[str]] = {}
    for file_path in sorted(path for path in root.rglob('*') if path.is_file()):
        destination = str(Path('share') / package_name / file_path.parent.relative_to(source_root))
        collected.setdefault(destination, []).append(str(file_path))
    return list(collected.items())


setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ] + collect_files('launch') + collect_files('config', anchor=WORKSPACE_ROOT) + collect_files('docs', anchor=WORKSPACE_ROOT),
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='chen',
    maintainer_email='chen@example.com',
    description='Bringup package for the desktop inspection workspace.',
    license='MIT',
)
