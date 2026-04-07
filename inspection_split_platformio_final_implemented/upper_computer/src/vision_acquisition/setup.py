from setuptools import setup
from glob import glob
import os

package_name = 'vision_acquisition'

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
        'sensor_msgs',
        'std_msgs',
        'cv_bridge',
        'opencv-python',
        'numpy'],
    zip_safe=True,
    maintainer='student',
    maintainer_email='student@example.com',
    description='Image acquisition nodes for camera or ESP32-S3 stream.',
    license='MIT',
    entry_points={
        'console_scripts': [
            "camera_node = vision_acquisition.camera_node:main"
        ],
    },
)
