from setuptools import setup, find_packages
from glob import glob

package_name = 'inspection_diagnostics'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(include=[package_name, f'{package_name}.*']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools', 'rclpy', 'std_msgs', 'sensor_msgs', 'inspection_interfaces', 'inspection_utils'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='Diagnostics aggregation for inspection station.',
    license='MIT',
    entry_points={'console_scripts': ['diagnostics_node = inspection_diagnostics.diagnostics_node:main']},
)
