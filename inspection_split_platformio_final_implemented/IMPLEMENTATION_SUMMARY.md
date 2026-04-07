# Split Implementation Summary

## Delivered structure
- `upper_computer/`: original ROS2 + gateway + frontend project, updated to support STM32 serial station and ESP32-S3 HTTP camera.
- `firmware/stm32_station_platformio/`: PlatformIO STM32 station firmware.
- `firmware/esp32s3_camera_platformio/`: PlatformIO ESP32-S3 camera firmware.
- `docs/`: split deployment, STM32 serial protocol, ESP32-S3 API docs.

## Host-side changes
- Added `Esp32HttpCameraProvider` to `vision_acquisition.camera_provider`.
- Added `camera_provider / esp32_base_url / esp32_snapshot_path / esp32_health_path / esp32_request_timeout_ms / esp32_auth_header / esp32_auth_token` camera parameters.
- Added `config/camera/camera_esp32s3.yaml`.
- Added `config/station/station_stm32.yaml`.
- Bringup/runtime resolution now forwards explicit `profile_config_path` into vision/decision/logger so profile loading stays consistent between source and install deployments.
- Runtime booleans are now normalized through deterministic parsing rather than Python truthiness on raw strings.
- Added tests covering ESP32 HTTP provider, profile-path propagation, split release manifest, and top-level delivery gates.

## Firmware-side changes
- STM32 firmware implements the existing framed serial protocol used by `station_bridge` and now executes feed/sort actions as a non-blocking state machine instead of blocking `HAL_Delay()` pulse calls inside the command path.
- ESP32-S3 firmware implements `/api/v1/camera/snapshot` and `/api/v1/camera/health`, adds Wi-Fi reconnect/self-heal telemetry, camera reinitialization on repeated snapshot failures, and token-based HTTP authentication with optional anonymous compatibility mode.

## Validation executed in this sandbox
- `python3 scripts/validate_split_environment.py --workspace-root . --mode ci --require-node`
- `python3 scripts/check_python_syntax.py`
- `bash scripts/run_backend_required_tests.sh`
- `bash scripts/run_backend_runtime_smoke_tests.sh`
- `python3 -m pytest -q src/inspection_tests`
- `npm --prefix frontend test`
- `npm --prefix frontend run typecheck`
- `npm --prefix frontend run lint`
- `npm --prefix frontend run build:real`

## Validation not executed here
- PlatformIO firmware build (`platformio` not installed in this sandbox)
- ROS2 Humble real hardware integration against STM32 + ESP32-S3 devices

## Split delivery governance
- Added top-level release manifest: `release/split_release_manifest.yaml`.
- Added top-level CI workflow: `.github/workflows/split_delivery_ci.yml`.
- Added packaging scripts: `scripts/build_source_package.sh`, `scripts/build_release_bundle.sh`.


## 新增发布真值源与环境预检
- 新增 `release/version_manifest.yaml` 作为 split delivery 版本与协议真值源。
- 顶层 `.github/workflows/split_delivery_ci.yml` 现补入 ROS2 Humble release gate 与固件契约测试。
- `scripts/validate_split_environment.py` 现支持 `dev/ci/release` 模式。
