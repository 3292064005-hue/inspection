#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/.tmp_firmware_contract"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

c++ -std=c++17 -Wall -Wextra -Werror \
  -I"$ROOT_DIR/firmware/stm32_station_platformio/lib/inspection_station_contract" \
  "$ROOT_DIR/firmware/tests/stm32_station_contract_test.cpp" \
  -o "$BUILD_DIR/stm32_contract_test"
"$BUILD_DIR/stm32_contract_test"

c++ -std=c++17 -Wall -Wextra -Werror \
  -I"$ROOT_DIR/firmware/esp32s3_camera_platformio/lib/inspection_camera_contract" \
  "$ROOT_DIR/firmware/tests/esp32_camera_contract_test.cpp" \
  -o "$BUILD_DIR/esp32_contract_test"
"$BUILD_DIR/esp32_contract_test"
