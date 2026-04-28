# Inspection HMI Frontend

面向桌面视觉质检与自动分拣工作站的前端工程。当前只保留这一份前端说明，历史升级摘要与阶段性架构说明已收敛到正式文档中。

## 技术栈
- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router
- Tailwind CSS
- ECharts

## 当前结构
```text
src/
  app/
    layouts/
    router/
  entities/
  features/
  mocks/
  pages/
  shared/
    config/
    gateway/
    types/
    utils/
  widgets/
```

## 网关接入模式
- `mock`：默认开发演示模式
- `http`：通过 REST + WebSocket 连接真实 HMI Gateway
- 网关消费入口：`upper_computer/frontend/src/shared/gateway/httpGateway.ts`
- 生成契约：`upper_computer/frontend/src/shared/gateway/generated/actionApi.ts`
- 契约同步：`python3 upper_computer/scripts/sync_gateway_contracts.py`

## 当前已落实的前端能力
- 运行首页、实时检测、结果追溯、统计分析、配方管理、设备诊断、系统设置
- `HttpGateway` 使用生成 client / routes 接入 canonical action plane
- SafeGateway / parse 入口用于运行时校验
- Query cache、连接横幅、危险动作确认、导出流、维护模式流程机
- 诊断页显式展示动作治理分级：正式 / 兼容 / 实验、lifecycle、execution policy、runtime truth

## 开发与构建
```bash
npm ci
npm run dev
npm run build
npm run test
npm run e2e
```

## 与真实后端对齐的约束
- 前端不要直接依赖 ROS2 原始 topic/service，统一通过 HMI Gateway 的 HTTP/WS 语义层接入
- 对外动作提交优先走 `/api/v1/actions/*` canonical action plane
- 前端不再依赖兼容 façade 或旧命令路由，所有对外动作统一走 canonical action plane

## 当前边界
- 本仓库已提供生成契约、前端治理分级显示和 mock / http 双模式
- 真实字段样例、frontend dist 发布产物、浏览器与真机联调仍需在目标环境验证
