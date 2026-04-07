from setuptools import setup, find_packages
from glob import glob
import os

package_name = 'station_bridge'

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
    install_requires=['setuptools', 'rclpy',
        'std_msgs',
        'inspection_interfaces',
        'pyserial'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='Hardware bridge for STM32 / fake station.',
    license='MIT',
    entry_points={
        'console_scripts': [
            "station_bridge_node = station_bridge.station_bridge_node:main"
        ],
    },
)
