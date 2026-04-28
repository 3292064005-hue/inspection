#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/dist"
mkdir -p "$OUT_DIR"
ARCHIVE_PATH="${OUT_DIR}/inspection_split_source_$(date +%Y%m%d_%H%M%S).tar.gz"

python3 "$ROOT_DIR/scripts/render_split_release_manifest.py" --workspace-root "$ROOT_DIR" --package-class source_delivery >/dev/null
python3 "$ROOT_DIR/scripts/render_split_release_manifest.py" --workspace-root "$ROOT_DIR" --package-class source_delivery --check

tar \
  --exclude='./dist' \
  --exclude='./upper_computer/frontend/node_modules' \
  --exclude='./upper_computer/frontend/dist' \
  --exclude='./upper_computer/.artifacts' \
  --exclude='./upper_computer/.pytest_cache' \
  --exclude='./upper_computer/build' \
  --exclude='./upper_computer/install' \
  --exclude='./upper_computer/log' \
  --exclude='./firmware/stm32_station_platformio/.pio' \
  --exclude='./firmware/esp32s3_camera_platformio/.pio' \
  --exclude='./.tmp_firmware_contract' \
  --exclude='**/__pycache__' \
  -czf "$ARCHIVE_PATH" \
  -C "$ROOT_DIR" .

echo "$ARCHIVE_PATH"
