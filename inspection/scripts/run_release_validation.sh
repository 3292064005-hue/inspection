#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
UPPER_DIR="${ROOT_DIR}/upper_computer"

log() {
  printf '[release-validation] %s\n' "$*"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    printf '[release-validation] missing required command: %s\n' "$1" >&2
    exit 1
  }
}

run_checked() {
  log "$*"
  "$@"
}

cd "${ROOT_DIR}"

require_cmd python3
require_cmd bash
require_cmd tar
require_cmd node
require_cmd npm
require_cmd colcon
require_cmd platformio

run_checked python3 scripts/validate_split_environment.py --workspace-root . --mode release --expect-ros humble --require-node --require-colcon --require-platformio
run_checked python3 scripts/render_split_release_manifest.py --workspace-root . --check
run_checked python3 scripts/validate_release_versions.py --workspace-root .
run_checked bash scripts/run_firmware_contract_tests.sh

log "building PlatformIO firmware projects"
run_checked platformio run -d firmware/stm32_station_platformio
run_checked platformio run -d firmware/esp32s3_camera_platformio

log "running upper_computer backend + ROS release validation"
run_checked bash "${UPPER_DIR}/scripts/run_backend_release_gate.sh"
run_checked bash "${UPPER_DIR}/scripts/validate_ros_workspace.sh"
run_checked bash "${UPPER_DIR}/scripts/run_ros2_humble_runtime_validation.sh"

log "building source and release bundles"
run_checked bash scripts/build_source_package.sh
run_checked bash scripts/build_release_bundle.sh

log "release validation finished successfully"
