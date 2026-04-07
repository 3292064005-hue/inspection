# 本轮重构说明

## 已完成
- 新增 `HttpGateway`，支持通过 REST + WebSocket 接入真实 HMI 网关。
- `service.ts` 支持 `mock` / `http` 双模式切换。
- `ConnectionBanner` 增加网关模式显示、心跳老化提示。
- 新增统一确认弹窗 `ConfirmDialog.vue`，替换高风险操作里的原生 `window.confirm`。
- 新增轻量缓存层 `src/shared/query/cache.ts`，用于结果、配方、诊断查询的缓存与失效控制。
- 配方页新增：
  - 未保存离页保护
  - 规则增删
  - 历史版本显示
  - 列表刷新
- 结果追溯页新增：
  - 筛选条件本地持久化
  - 客户端分页
  - 当前筛选结果导出 CSV
  - 原图 / 标注图切换
  - 批次摘要
- 诊断页新增：
  - 统一确认
  - 动作冷却时间
  - 维护模式锁
- 构建已通过：`npm run build`

## 新增环境变量
- `VITE_GATEWAY_MODE`
- `VITE_GATEWAY_BASE_URL`
- `VITE_GATEWAY_WS_URL`
- `VITE_GATEWAY_REQUEST_TIMEOUT_MS`
- `VITE_HEARTBEAT_OFFLINE_MS`
- `VITE_HEARTBEAT_DEGRADED_MS`
- `VITE_DEMO_SCENARIO`

## 真实网关建议接口
### HTTP
- `GET /api/station/snapshot`
- `GET /api/station/stats`
- `POST /api/station/start`
- `POST /api/station/stop`
- `POST /api/station/reset-fault`
- `POST /api/station/new-batch`
- `GET /api/results?...query`
- `GET /api/recipes`
- `POST /api/recipes`
- `POST /api/recipes/:id/activate`
- `GET /api/diagnostics`
- `POST /api/diagnostics/actions`
- `POST /api/export/:batchId`

### WebSocket
消息结构兼容：
```json
{ "event": "station.state.updated", "payload": { ... } }
```
或：
```json
{ "type": "station.state.updated", "data": { ... } }
```
