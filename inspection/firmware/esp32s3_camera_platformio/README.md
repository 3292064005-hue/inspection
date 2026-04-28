# ESP32-S3 Camera Firmware (PlatformIO)

## 目标职责
- 作为无线相机节点，向上位机提供：
  - `GET /api/v1/camera/snapshot`
  - `GET /api/v1/camera/health`
- 上位机通过 `Esp32HttpCameraProvider` 拉取 JPEG 图像

## 关键配置
- PlatformIO board：`esp32s3_n16r8`
- 默认 camera preset：`INSPECTION_CAMERA_PRESET_XIAO_SENSE`
- 相机与 Wi-Fi 配置：`firmware/esp32s3_camera_platformio/include/inspection_camera_config.h`
- runtime policy lib：`firmware/esp32s3_camera_platformio/lib/inspection_camera_runtime/inspection_camera_runtime.hpp`

## 常用命令
```bash
pio run
pio test -e native
```

## 说明
- 如果不是 Seeed XIAO ESP32S3 Sense，先调整 preset build flag 或配置头文件。
- 默认鉴权 Header：`X-Inspection-Token`。
