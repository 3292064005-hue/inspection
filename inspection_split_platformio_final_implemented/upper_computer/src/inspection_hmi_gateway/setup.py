from setuptools import find_packages, setup
from glob import glob
from pathlib import Path

package_name = 'inspection_hmi_gateway'
package_root = Path(__file__).resolve().parent
workspace_root = package_root.parent.parent


def collect_files(source: Path, destination: str) -> list[tuple[str, list[str]]]:
    if not source.exists():
        return []
    collected: list[tuple[str, list[str]]] = []
    for file_path in sorted(path for path in source.rglob('*') if path.is_file()):
        relative_parent = file_path.relative_to(source).parent
        target_dir = Path(destination, str(relative_parent)) if str(relative_parent) != '.' else Path(destination)
        collected.append((target_dir.as_posix(), [str(file_path)]))
    return collected


data_files = [
    ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
    ('share/' + package_name, ['package.xml']),
    ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
]

data_files += collect_files(workspace_root / 'frontend' / 'dist', f'share/{package_name}/frontend/dist')
data_files += collect_files(workspace_root / 'config' / 'recipes', f'share/{package_name}/config/recipes')
data_files += collect_files(workspace_root / 'config' / 'system', f'share/{package_name}/config/system')

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(include=[package_name, f'{package_name}.*']),
    data_files=data_files,
    install_requires=['setuptools', 'rclpy', 'std_msgs', 'sensor_msgs', 'inspection_interfaces', 'inspection_utils', 'fastapi', 'uvicorn', 'pyyaml'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='HTTP/WebSocket gateway for inspection HMI frontend.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'inspection_hmi_gateway_server = inspection_hmi_gateway.main:main',
            'inspection_action_executor_node = inspection_hmi_gateway.action_executor_node:main',
        ],
    },
)
