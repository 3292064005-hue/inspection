# UPGRADE NOTES V2

## 本轮重构重点

### 1. 连接层升级
- 增加了 `HttpClient` 与 `GatewayWebSocketClient`
- `HttpGateway` 不再是简单 fetch + WebSocket 拼接，而是带有：
  - 请求超时
  - WebSocket 状态快照
  - 自动重连
  - 指数退避
  - 重连状态反馈
- `SafeGateway` 负责网关数据的运行时校验与错误上报

### 2. 数据校验升级
- 原先的手写 type guard 已重构为结构化 `parse*` 系列函数
- 校验错误会被归类为 `GatewayError`
- 事件流、查询结果、诊断动作、配方数据都统一走校验入口

### 3. 查询缓存升级
- `shared/query/cache.ts` 增加：
  - in-flight 去重
  - 过期控制
  - allowStale + 后台刷新入口
  - key 列表与前缀失效

### 4. 状态流程增强
- 新增轻量流程机：
  - `processes/app-session/machine.ts`
  - `processes/maintenance-mode/machine.ts`
  - `processes/export-flow/machine.ts`
- 没有强塞额外依赖，但先把流程边界明确下来，后续如果接入 XState 会更平滑

### 5. 页面级增强
#### 结果追溯页
- 筛选模板保存 / 恢复 / 删除
- 分页大小切换
- 当前页 / 全量导出
- 复制二维码 / 结果 ID
- 批次摘要增强

#### 配方页
- 修改人 / 修改说明
- 差异预览
- 草稿本地保存
- 离页保护（路由守卫）
- 历史版本备注展示

#### 诊断页
- 维护模式剩余时间
- 维护状态机展示
- 动作冷却
- 危险动作统一确认

#### Demo 页
- 支持 mock 场景切换：balanced / stress / throughput

#### 设置页
- 展示缓存条目数
- 展示重连参数
- 清空 query cache + localStorage

### 6. UI / 构建优化
- `ConnectionBanner` 展示 HTTP / WS 状态、重连次数
- `KpiChart` 改为 `ResizeObserver` 驱动 resize
- 工程已实际执行 `npm ci` + `npm run build`

## 这轮仍未完全封死的点
- 还没有接入真实后端协议字段样例
- 还没有补 Vitest / Playwright 自动化测试链
- 如果你后续提供真实 REST / WebSocket 协议，我可以继续把 mock / real 接口完全对齐
