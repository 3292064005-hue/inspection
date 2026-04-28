#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALLOW_UNVALIDATED=0
if [[ "${1:-}" == "--allow-unvalidated" ]]; then
  ALLOW_UNVALIDATED=1
  shift
fi
OUT_DIR="${ROOT_DIR}/dist"
mkdir -p "$OUT_DIR"
BUILD_KIND="formal_release"
ARCHIVE_STEM="inspection_split_release"
if [[ "$ALLOW_UNVALIDATED" -eq 1 ]]; then
  BUILD_KIND="internal_unvalidated"
  ARCHIVE_STEM="inspection_split_release_internal_unvalidated"
fi
ARCHIVE_PATH="${OUT_DIR}/${ARCHIVE_STEM}_$(date +%Y%m%d_%H%M%S).tar.gz"

REQUIRED_PATHS=(
  README.md
  docs/SPLIT_DEPLOYMENT.md
  docs/STM32_SERIAL_PROTOCOL.md
  docs/ESP32S3_CAMERA_API.md
  upper_computer/README.md
  upper_computer/docs/ARCHITECTURE.md
  upper_computer/frontend/README.md
  firmware/stm32_station_platformio/README.md
  firmware/esp32s3_camera_platformio/README.md
  release/split_release_manifest.yaml
  release/runtime_validation_matrix.yaml
)

if [[ "$ALLOW_UNVALIDATED" -ne 1 ]]; then
  REQUIRED_PATHS+=(
    release/runtime_validation_evidence/gate_status.json
    release/runtime_validation_evidence/audit_summary.json
    upper_computer/frontend/dist/index.html
  )
  python3 "$ROOT_DIR/scripts/validate_runtime_validation_matrix.py" --workspace-root "$ROOT_DIR"
  python3 "$ROOT_DIR/scripts/run_runtime_validation_matrix.py" --workspace-root "$ROOT_DIR" --strict-hardware-evidence >&2
  python3 "$ROOT_DIR/scripts/render_runtime_validation_audit.py" --workspace-root "$ROOT_DIR" --check-ready >&2
  python3 "$ROOT_DIR/scripts/render_split_release_manifest.py" --workspace-root "$ROOT_DIR" --package-class formal_runnable_release >/dev/null
  python3 "$ROOT_DIR/scripts/render_split_release_manifest.py" --workspace-root "$ROOT_DIR" --package-class formal_runnable_release --check
else
  printf '[WARN] building internal unvalidated release bundle; formal release evidence gate is bypassed.\n' >&2
  python3 "$ROOT_DIR/scripts/validate_runtime_validation_matrix.py" --workspace-root "$ROOT_DIR"
  python3 "$ROOT_DIR/scripts/run_runtime_validation_matrix.py" --workspace-root "$ROOT_DIR" --skip-sim-execution --allow-missing-hardware-evidence >&2
  python3 "$ROOT_DIR/scripts/render_runtime_validation_audit.py" --workspace-root "$ROOT_DIR" >&2
  python3 "$ROOT_DIR/scripts/render_split_release_manifest.py" --workspace-root "$ROOT_DIR" >/dev/null
  python3 "$ROOT_DIR/scripts/render_split_release_manifest.py" --workspace-root "$ROOT_DIR" --check
fi

for relative_path in "${REQUIRED_PATHS[@]}"; do
  if [[ ! -e "${ROOT_DIR}/${relative_path}" ]]; then
    printf 'missing required release bundle input: %s\n' "$relative_path" >&2
    exit 1
  fi
done

TAR_EXCLUDES=(
  --exclude='upper_computer/frontend/node_modules'
  --exclude='upper_computer/frontend/node_modules/*'
  --exclude='upper_computer/.artifacts'
  --exclude='upper_computer/.artifacts/*'
  --exclude='upper_computer/.pytest_cache'
  --exclude='upper_computer/.pytest_cache/*'
  --exclude='upper_computer/build'
  --exclude='upper_computer/build/*'
  --exclude='upper_computer/install'
  --exclude='upper_computer/install/*'
  --exclude='upper_computer/log'
  --exclude='upper_computer/log/*'
  --exclude='firmware/stm32_station_platformio/.pio'
  --exclude='firmware/stm32_station_platformio/.pio/*'
  --exclude='firmware/esp32s3_camera_platformio/.pio'
  --exclude='firmware/esp32s3_camera_platformio/.pio/*'
  --exclude='.tmp_firmware_contract'
  --exclude='.tmp_firmware_contract/*'
  --exclude='**/__pycache__'
)

if [[ "$ALLOW_UNVALIDATED" -eq 1 ]]; then
  TAR_EXCLUDES+=(
    --exclude='upper_computer/frontend/dist'
    --exclude='upper_computer/frontend/dist/*'
  )
fi

tar \
  "${TAR_EXCLUDES[@]}" \
  -czf "$ARCHIVE_PATH" \
  -C "$ROOT_DIR" \
  README.md docs firmware upper_computer release scripts .github

printf '%s\n' "$ARCHIVE_PATH"
printf '[INFO] release bundle kind=%s\n' "$BUILD_KIND" >&2
