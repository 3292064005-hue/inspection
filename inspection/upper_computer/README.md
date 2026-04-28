# Desktop Inspection Workspace

基于 ROS2 的桌面视觉质检与自动分拣工作站上位机工程。本文只保留运行、验证和契约入口；架构细节收敛到 `upper_computer/docs/ARCHITECTURE.md`。

## 工作区结构

- `inspection_supervisor`：系统级健康、模式与恢复建议。
- `inspection_orchestrator`：启动、自动运行、维护与恢复编排。
- `inspection_diagnostics`：统一健康快照与诊断 topic 聚合。
- `inspection_interfaces`：ROS message / service / action 定义。
- `inspection_bringup`：真实站、仿真和离线回放 launch 入口。
- `vision_acquisition`：图像采集，支持 mock 与 ESP32-S3 HTTP snapshot。
- `vision_processing`：规则视觉检测、插件注册与结果摘要。
- `inspection_decision`：业务判定与分拣映射。
- `station_bridge`：STM32 串口桥接与 mock 工位协议层。
- `inspection_fsm`：单件状态机调度核心。
- `inspection_logger`：日志、结果、图像、trace、bag 与 read model 写入。
- `inspection_hmi_gateway`：HTTP / WebSocket 网关、action plane、前端契约与认证。
- `inspection_hmi`：轻量状态面板节点。
- `inspection_sim`：仿真图像与联调辅助。
- `inspection_tests`：算法、协议、状态机、Gateway 与发布契约测试。

## 环境基线

- OS：Ubuntu 22.04 LTS
- ROS2：Humble Hawksbill
- Python：3.10+
- Node.js：20 LTS / 22 LTS
- 浏览器烟测：Playwright + Chromium

Windows 可以跑大部分 Python/前端沙箱测试，但正式 ROS2、colcon、硬件闭环与发布验证仍以 Ubuntu 22.04 + ROS2 Humble 为准。

## 常用运行

真实站：

```bash
cd upper_computer
bash scripts/build_frontend.sh real
colcon build
source install/setup.bash
ros2 launch inspection_bringup real_station.launch.py profile_name:=production
```

仿真栈：

```bash
cd upper_computer
ros2 launch inspection_bringup sim_stack.launch.py profile_name:=simulation
```

离线回放：

```bash
cd upper_computer
ros2 launch inspection_bringup offline_replay.launch.py profile_name:=benchmark
```

Simulation runtimes must use `station_capability_profile: simulation_station_default` so mock adapter expectations stay aligned with fail-closed station capability validation.

## 验证入口

- 日常快检：`bash scripts/validate_workspace.sh`
- 后端 required gate：`bash scripts/run_backend_required_tests.sh`
- 后端 release gate：`bash scripts/run_backend_release_gate.sh`
- 前端检查：`cd frontend && npm test && npm run typecheck && npm run lint && npm run build:mock`
- 前端 Playwright 烟测：`bash scripts/run_frontend_e2e.sh`
- launch matrix：`bash scripts/run_launch_test_matrix.sh`
- ROS release 预检：`python scripts/ros_release_gate_preflight.py --workspace-root . --require-colcon --require-frontend-dist`
- ROS2/Humble runtime gate：`bash scripts/run_ros2_humble_runtime_validation.sh`

`ros_release_gate_preflight.py` 会写出 `ros_release_preflight.json` 或 `ros_runtime_preflight.json`，用于区分构建预检和运行时预检证据。

## Gateway 契约与治理真值

- 单一真值源：`upper_computer/config/system/action_registry.yaml`
- 派生治理资产：`upper_computer/config/system/action_capability_matrix.yaml`、`upper_computer/config/system/action_governance.yaml`、`upper_computer/config/system/compatibility_routes.yaml`、`upper_computer/config/system/station_capability_expectations.yaml`
- Gateway 派生资产：`upper_computer/frontend/openapi/inspection_gateway_openapi.json`、`upper_computer/frontend/src/shared/gateway/generated/actionApi.ts`
- transport 策略：`upper_computer/config/system/transport_bridge_policy.yaml`
- 同步：`python scripts/sync_action_registry.py && python scripts/sync_gateway_contracts.py`
- 检查：`python scripts/sync_action_registry.py --check && python scripts/check_gateway_contract_drift.py`

兼容 HTTP 路由已从运行时删除；所有对外动作统一走 `/api/v1/actions/*` canonical action plane。`run_benchmark` 是内部 synthetic QA / performance tooling，不计入生产吞吐。

## HMI 鉴权与运行目录

- HMI 用户配置：`upper_computer/config/system/hmi_users.yaml`
- runtime root 优先级：`$INSPECTION_RUNTIME_ROOT` -> `$ROS_HOME/inspection` -> `${XDG_STATE_HOME:-~/.local/state}/inspection`
- 若 runtime root 下缺少用户文件，Gateway 会生成一次性 bootstrap admin 到 `logs/runtime/bootstrap/bootstrap_admin.yaml`
- 源码交付包默认不强制 `upper_computer/frontend/dist/index.html` 存在；只有显式开启 `require_frontend_dist:=true` 或 `INSPECTION_HMI_REQUIRE_FRONTEND_DIST=1` 时，Gateway 才会在缺少 dist 时启动失败。

## 动作与诊断开关

- `INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED=1`：统一 action transport 不可用时，显式允许 Gateway 回退到本地 runtime；默认关闭。
- `INSPECTION_RESULT_CREATED_ALIAS_ENABLED=0|1`：控制 `inspection.result.created` 兼容别名是否广播；默认不广播，第一方消费者与 mock 演示链使用 `inspection.result.finalized`。
- `INSPECTION_TRANSPORT_LEGACY_ENABLED=1`：typed-first transport 的全局 legacy publish 回滚开关。
- `enable_annotated_image_diagnostics:=true|false`：`real_station.launch.py` 与 `offline_replay.launch.py` 的 annotated 图像诊断订阅开关，默认 `false`。

## 关键 Topic

- `/inspection/camera/status`：相机链路健康与 snapshot 状态。
- `/inspection/result_raw`：视觉处理原始结果输出，诊断旁路，默认不纳入 core rosbag 录制。
- `/inspection/image_annotated`：annotated 图像诊断流，只在 `enable_annotated_image_diagnostics:=true` 时订阅，默认不纳入 core rosbag 录制。

## 当前实现边界

- 上位机采用 canonical action plane、generated gateway contract、治理分级矩阵和 typed-first transport 边界。
- 真实 ROS2 Humble、frontend dist、真机联机与硬件异常注入仍需在目标环境完成。
- 不要把 `.artifacts/verification/verification_manifest.json` 之外的旧报告或过程文档当作发布真值。
