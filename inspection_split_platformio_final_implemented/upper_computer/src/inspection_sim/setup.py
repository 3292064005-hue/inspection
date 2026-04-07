from setuptools import setup
from glob import glob
import os

package_name = 'inspection_sim'

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
        'std_msgs'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='Simulation helpers and offline sample publisher.',
    license='MIT',
    entry_points={
        'console_scripts': [
            "sim_cycle_driver = inspection_sim.sim_cycle_driver:main"
        ],
    },
)
