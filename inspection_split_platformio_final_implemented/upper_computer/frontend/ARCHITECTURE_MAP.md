# 前端架构升级说明

本次升级把原先的“页面直接调 gateway + 单一 mock 演示骨架”收敛为更稳定的 HMI 前端底座：

- 新增 **SafeGateway**，对入站事件和查询结果做运行时校验。
- 修复 mock 运行循环的调度方式，避免停止后残留阶段更新继续写回 UI。
- 新增 **App Store**，统一管理连接态、维护模式、通知和最近导出路径。
- 页面不再直接调用 gateway，统一改走 feature/action 层：
  - `useStationControl`
  - `useResultTrace`
  - `useRecipeManagement`
  - `useDiagnostics`
- 运行页、追溯页、配方页、诊断页、统计页全部补了连接横幅与更明确的交互状态。
- 诊断页支持维护模式锁定与测试动作入口，为后续接真实 ROS2/HMI 网关预留扩展点。
