#!/usr/bin/env bash
set -euo pipefail
source /opt/ros/humble/setup.bash
cd "$(dirname "$0")/.."
export INSPECTION_HMI_PORT=${INSPECTION_HMI_PORT:-8080}
ros2 launch inspection_hmi_gateway hmi_gateway.launch.py \
  action_executor_enabled:=${INSPECTION_ACTION_EXECUTOR_ENABLED:-true} \
  native_action_client_enabled:=${INSPECTION_NATIVE_ACTION_CLIENT_ENABLED:-true} \
  native_action_server_enabled:=${INSPECTION_NATIVE_ACTION_SERVER_ENABLED:-true} \
  log_root:=${INSPECTION_HMI_LOG_ROOT:-logs/runtime} \
  recipe_root:=${INSPECTION_HMI_RECIPE_ROOT:-config/recipes} \
  frontend_dist:=${INSPECTION_HMI_FRONTEND_DIST:-frontend/dist} \
  users_path:=${INSPECTION_HMI_USERS_PATH:-config/system/hmi_users.yaml}
