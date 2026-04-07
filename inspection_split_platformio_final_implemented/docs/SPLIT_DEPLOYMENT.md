# Split Deployment Guide

## 上位机 ↔ STM32
- 物理链路：USB CDC / UART
- 默认串口：`/dev/ttyUSB0`
- 默认波特率：`115200`
- 协议格式：`inspection_utils.protocol` 中的帧协议
- 命令：
  - `CMD_FEED_ONE (0x10)`
  - `CMD_SORT_TO_BIN (0x20)`
  - `CMD_RESET_FAULT (0x40)`
  - `CMD_QUERY_CAPABILITIES (0x41)`
  - `CMD_HEARTBEAT (0x7E)`
- 响应：
  - `RSP_ACK (0x80)`
  - `RSP_NACK (0x81)`
  - `RSP_POSITION_READY (0x90)`
  - `RSP_SORT_DONE (0x91)`
  - `RSP_HEARTBEAT (0x92)`
  - `RSP_CAPABILITIES (0x93)`
  - `RSP_FAULT (0xE0)`

## 上位机 ↔ ESP32-S3
- 物理链路：Wi-Fi / HTTP
- snapshot：`GET /api/v1/camera/snapshot`
- health：`GET /api/v1/camera/health`
- 上位机 provider：`Esp32HttpCameraProvider`

## 推荐配置文件
- STM32：`upper_computer/config/station/station_stm32.yaml`
- ESP32-S3：`upper_computer/config/camera/camera_esp32s3.yaml`

## 发布与兼容矩阵
- 顶层发布清单：`release/split_release_manifest.yaml`
- 顶层 CI 会同时验证：上位机、ROS2 Humble runtime、两套 PlatformIO 固件、固件契约测试、协议回归
- 当前协议回归主测试：`upper_computer/src/inspection_tests/test_protocol.py`

## ESP32-S3 接口安全与配置
- 默认鉴权 Header：`X-Inspection-Token`（可通过固件 build flag 覆盖）
- 默认不允许匿名 HTTP 访问；如需实验兼容模式，显式设置 `INSPECTION_ALLOW_ANONYMOUS_HTTP=1`
- 建议通过 `platformio_override.ini` 或 CI/build flags 提供：
  - `INSPECTION_WIFI_SSID`
  - `INSPECTION_WIFI_PASSWORD`
  - `INSPECTION_HTTP_AUTH_TOKEN`
