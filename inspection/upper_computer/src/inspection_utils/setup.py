from setuptools import setup
from glob import glob
import os

package_name = 'inspection_utils'

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
        'PyYAML',
        'opencv-python',
        'numpy'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='Common utilities for inspection station.',
    license='MIT',
    entry_points={
        'console_scripts': [
            "recipe_cli = inspection_utils.recipe_tools:main"
        ],
    },
)
