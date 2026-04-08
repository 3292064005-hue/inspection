from setuptools import setup, find_packages
from glob import glob
import os

package_name = 'vision_processing'

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
        'sensor_msgs',
        'std_msgs',
        'cv_bridge',
        'opencv-python',
        'numpy',
        'PyYAML',
        'inspection_utils',
        'inspection_interfaces'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='Rule-based visual inspection pipeline.',
    license='MIT',
    entry_points={
        'console_scripts': [
            "vision_processor_node = vision_processing.processor_node:main"
        ],
    },
)
