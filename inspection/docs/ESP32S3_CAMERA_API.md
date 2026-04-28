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


## 请求示例
### 鉴权 snapshot
```bash
curl -H 'X-Inspection-Token: <token>'   http://<camera-host>/api/v1/camera/snapshot   --output snapshot.jpg
```

### health
```bash
curl -H 'X-Inspection-Token: <token>'   http://<camera-host>/api/v1/camera/health
```

## 失败响应示例
### 401
当固件启用了 HTTP 鉴权、请求未提供 `X-Inspection-Token`，或提供了错误 token 时，当前实现统一返回 `401`，并带 `WWW-Authenticate: InspectionToken` 头；返回体会区分 `missing_token` 与 `invalid_token`，例如：
```json
{"authorized":false,"reason":"missing_token"}
```
或：
```json
{"authorized":false,"reason":"invalid_token"}
```

### 403
当前固件实现不使用 `403` 表示 token 缺失或错误；若未来增加基于角色或模式的访问拒绝，再单独定义 `403` 语义。

### 503
当拍照失败、相机重初始化失败或设备处于降级状态时，`snapshot` 可返回 503，例如：
```json
{"error":"capture_failed_reinitialized","degradedReason":"camera_reinitialized"}
```
