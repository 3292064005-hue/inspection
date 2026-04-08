# ESP32-S3 Camera Firmware (PlatformIO)

## 目标职责
- 作为无线相机节点，向上位机提供：
  - `GET /api/v1/camera/snapshot`
  - `GET /api/v1/camera/health`
- 上位机通过 `Esp32HttpCameraProvider` 拉取 JPEG 图像

## 当前默认预设
- PlatformIO board: `esp32s3_n16r8`
- 默认 camera pin preset: `INSPECTION_CAMERA_PRESET_XIAO_SENSE`

## 注意
- 你如果不是 Seeed XIAO ESP32S3 Sense，请先改 `include/inspection_camera_config.h` 或 `platformio.ini` 的 preset build flag。
- Wi-Fi SSID/密码也在 `inspection_camera_config.h` 里改。

- 默认鉴权 Header：`X-Inspection-Token`
