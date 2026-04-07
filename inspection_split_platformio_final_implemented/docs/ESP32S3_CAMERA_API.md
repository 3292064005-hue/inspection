# ESP32-S3 Camera API

默认情况下，HTTP API 需要通过 `X-Inspection-Token`（可配置）进行鉴权。若固件显式启用了 `INSPECTION_ALLOW_ANONYMOUS_HTTP=1`，则可兼容匿名访问。

## `GET /api/v1/camera/snapshot`
- 返回：`image/jpeg`
- 用途：上位机按固定节拍轮询，替代本地 USB 摄像头
- 失败时：返回 `503` 与 JSON 原因（如 `capture_failed` / `capture_failed_reinitialized`）

## `GET /api/v1/camera/health`
- 返回 JSON：
```json
{
  "deviceId":"esp32s3-cam-01",
  "firmwareVersion":"esp32s3-camera-pio-v1",
  "cameraOk":true,
  "framesServed":123,
  "cameraFailures":0,
  "wifiConnected":true,
  "wifiConfigured":true,
  "reconnectCount":1,
  "cameraReinitCount":0,
  "lastSnapshotOk":true,
  "wifiRssi":-45,
  "uptimeMs":123456,
  "authEnabled":true,
  "authHeader":"X-Inspection-Token",
  "degradedReason":"none"
}
```

## 建议 build flag
- `INSPECTION_WIFI_SSID`
- `INSPECTION_WIFI_PASSWORD`
- `INSPECTION_HTTP_AUTH_TOKEN`
- `INSPECTION_HTTP_AUTH_HEADER`
- `INSPECTION_ALLOW_ANONYMOUS_HTTP`
