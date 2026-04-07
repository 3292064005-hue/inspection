from setuptools import setup
from glob import glob
import os

package_name = 'inspection_decision'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
        ('share/' + package_name + '/config', glob('config/*.yaml')),
    ],
    install_requires=['setuptools', 'rclpy',
        'inspection_interfaces',
        'inspection_utils',
        'PyYAML'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='Decision engine for OK/NG/RECHECK sorting.',
    license='MIT',
    entry_points={
        'console_scripts': [
            "decision_node = inspection_decision.decision_node:main"
        ],
    },
)
