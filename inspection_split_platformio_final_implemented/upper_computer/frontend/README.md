# Inspection HMI Frontend

面向“基于 ROS2 的桌面视觉质检与自动分拣工作站”的前端工程骨架。  
这版直接按工位 HMI 思路重建，不按普通后台管理系统写。

## 1. 技术栈

- Vue 3
- TypeScript
- Vite
- Pinia
- Vue Router
- Tailwind CSS
- ECharts

## 2. 当前已实现

- 运行首页（工位主控）
- 实时检测页
- 结果追溯页
- 统计分析页
- 配方管理页
- 设备诊断页
- 系统设置页
- 答辩展示页
- Mock Gateway 实时状态模拟
- 主按钮状态机切换
- 故障锁定 / 复位逻辑
- 最近样本流
- 事件时间轴
- 规则解释与节拍拆解
- 配方切换与保存入口

## 3. 目录结构

```text
src/
  app/
    layouts/
    router/
  entities/
    station/
    inspection/
    recipe/
    fault/
    settings/
  features/
    bootstrap/
  mocks/
  pages/
  shared/
    config/
    gateway/
    types/
    utils/
  widgets/
```

## 4. 运行方式

```bash
npm install
npm run dev
```

默认使用 mock 模式。真实网关接入时，只需要替换：

- `src/shared/gateway/service.ts`
- 新增 HTTP + WebSocket 适配器实现 `HmiGateway`

## 5. 和计划书的接口映射

### 计划书 ROS2 Topic / Service
- `/inspection/result`
- `/inspection/defect_type`
- `/station/state`
- `/station/count_stats`
- `/inspection/start`
- `/inspection/reset_fault`

### 前端语义层事件
- `inspection.result.created`
- `station.state.updated`
- `station.count.updated`
- `fault.raised`
- `fault.cleared`
- `camera.frame`
- `system.heartbeat`

建议由本地 HMI Gateway 完成 ROS2 → WebSocket/HTTP 的语义映射，前端不要直接耦合 ROS2 原始消息。

## 6. 后续你需要接真实后端时怎么改

### A. 启动 / 停止 / 复位
把以下方法替换为真实 HTTP 请求：
- `startStation()`
- `stopStation()`
- `resetFault()`
- `newBatch()`
- `exportBatch()`

### B. 状态 / 图像 / 结果
把以下事件替换为真实 WebSocket：
- `station.state.updated`
- `station.count.updated`
- `inspection.result.created`
- `camera.frame`
- `system.heartbeat`
- `fault.raised`

### C. 配方
真实接入时建议保留当前结构化表单模型，不要一开始做复杂拖拽式编辑器。

## 7. 当前这一版的定位

这不是最终商业版，而是一版：
- 能跑
- 能演示
- 能扩展
- 能和 ROS2 网关快速对接
- 不会把主控 UI 写乱的工程骨架

## 8. 建议的下一步

1. 先把网关层和 ROS2 topic / service 真对上。
2. 再把结果追溯和导出接到实际日志目录。
3. 最后补维护模式的二次确认和权限隔离。
