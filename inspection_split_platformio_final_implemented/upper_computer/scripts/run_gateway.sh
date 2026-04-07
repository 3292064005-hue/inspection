#!/usr/bin/env bash
set -e
source /opt/ros/humble/setup.bash
cd "$(dirname "$0")/.."
export INSPECTION_HMI_PORT=${INSPECTION_HMI_PORT:-8080}
ros2 run inspection_hmi_gateway inspection_hmi_gateway_server
