#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/.artifacts/verification"
cd "$ROOT_DIR"

python3 "$ROOT_DIR/scripts/ros_release_gate_preflight.py" --workspace-root "$ROOT_DIR" --require-frontend-dist --require-install-setup --write-json "$ARTIFACT_DIR/ros_runtime_preflight.json"

source /opt/ros/humble/setup.bash
source install/setup.bash

bash "$ROOT_DIR/scripts/run_ros_typed_interface_import_smoke.sh"

: "${COLCON_TEST_RESULT_BASE:=$ROOT_DIR/test_results}"
export INSPECTION_ACTION_EXECUTOR_ENABLED=true
export INSPECTION_REQUIRE_FRONTEND_DIST=1
export INSPECTION_HMI_REQUIRE_FRONTEND_DIST=1
export INSPECTION_HMI_STRICT_USER_CONFIG=1
export INSPECTION_REQUIRE_TYPED_INTERFACES=1
export PYTHONUNBUFFERED=1

bash "$ROOT_DIR/scripts/run_launch_test_matrix.sh"
