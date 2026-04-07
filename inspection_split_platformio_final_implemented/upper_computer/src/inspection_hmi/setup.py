from setuptools import setup
from glob import glob
import os

package_name = 'inspection_hmi'

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
        'std_msgs',
        'inspection_interfaces'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='Lightweight HMI/status dashboard node.',
    license='MIT',
    entry_points={
        'console_scripts': [
            "hmi_node = inspection_hmi.hmi_node:main"
        ],
    },
)
