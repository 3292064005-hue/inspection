# Desktop Inspection Workspace

基于 ROS2 的桌面视觉质检与自动分拣工作站源码（平台化增强版，含 native runtime bridge）。

## V8 关键增强
- **Supervisor / Orchestrator**：新增系统级监督与编排层，单件节拍继续由 FSM 控制，系统模式切换由 supervisor/orchestrator 统一管理；FSM 与 Orchestrator 已统一接入 managed runtime 生命周期治理。
- **Diagnostics**：新增聚合式健康快照节点，统一发布 bridge、vision、fault backlog、mode 等诊断状态。
- **Profile 运行模式**：继续支持 `production / debug / benchmark`，bringup 现在会先物化 effective config，再把 profile 覆盖项下发到 camera / station / fsm / decision / logger。
- **Bridge Session**：在 v7 的 session 基础上继续为 supervisor/diagnostics 暴露 session 与 pending command 细节。
- **Replay / Bag 支撑**：logger 新增可选 rosbag2 命令生成与启动能力，为后续回放回归打底。
- **Bringup 增强**：`real_station.launch.py`、`sim_stack.launch.py` 和 `offline_replay.launch.py` 都走安装态可导入的 bringup builder；`offline_replay` 默认资源路径与 profile 快照路径已绝对化，并接入 managed runtime 参数。

## 已实现主线
- 单工位、单相机、规则视觉、2+1 类分拣（OK / NG / RECHECK）
- ROS2 状态机调度：READY -> FEED_WAIT_ACK -> POSITION_WAIT -> CAPTURE_WAIT_FRAME -> ANALYZE_WAIT -> DECISION_WAIT -> SORT_WAIT_ACK -> SORT_WAIT_DONE -> COUNT_UPDATE
- 图像链路与控制链路解耦
- 配方化视觉参数与决策参数
- 结构化日志、结果落盘、标注图保存、trace 回放与 regression 基础能力
- 假硬件模式，可在无 STM32 / ESP32-S3 时联调

## 工作区结构
- `inspection_supervisor`：系统级健康、模式与恢复建议
- `inspection_orchestrator`：系统级启动 / 自动运行 / 维护 / 恢复编排
- `inspection_diagnostics`：统一健康快照发布
- `inspection_interfaces`：消息与服务定义
- `inspection_bringup`：统一启动文件
- `vision_acquisition`：图像采集
- `vision_processing`：规则视觉检测与缓存触发式采图
- `inspection_decision`：业务判定与分拣映射
- `station_bridge`：硬件桥接 / 假工位协议层
- `inspection_fsm`：工位状态机调度核心
- `inspection_logger`：日志、结果、图像归档与 trace / bag 支撑
- `inspection_hmi`：轻量状态面板节点
- `inspection_sim`：仿真图像与联调辅助
- `inspection_tests`：算法、协议、状态机与平台核心单元测试

## 运行环境基线
- OS：Ubuntu 22.04 LTS
- ROS2：Humble Hawksbill
- Python：3.10+
- 前端 Node.js：20 LTS / 22 LTS（依赖由 `package-lock.json` 锁定）
- 浏览器烟测：Playwright + Chromium（CI 或本地显式开启）

## 推荐运行
```bash
cd <workspace_root>
bash scripts/build_frontend.sh real
colcon build
source install/setup.bash
ros2 launch inspection_bringup real_station.launch.py profile_name:=production
# 或使用新的显式模拟整栈入口
ros2 launch inspection_bringup sim_stack.launch.py profile_name:=production
```

## 资产状态分级
- 资产状态清单见 `docs/REPOSITORY_ASSET_STATUS.md`。
- 运行/发布优先参考 **主链有效资产**；兼容保留与自动生成资产不得替代当前代码事实。

## 目录约定
- `config/system/system.yaml`：系统级参数
- `config/camera/camera.yaml`：采集参数
- `config/station/station.yaml`：工位与串口参数
- `config/recipes/default_recipe.yaml`：默认配方
- `config/profiles/*.yaml`：运行 profile
- 只读资源默认从已安装包 share 目录解析；launch 也允许显式绝对路径覆盖
- 可写运行目录默认解析到：工作区根（源码态）→ `$INSPECTION_RUNTIME_ROOT` → `$ROS_HOME/inspection` → `${XDG_STATE_HOME:-~/.local/state}/inspection`
- `logs/runtime/` 仍是源码态默认运行目录名，但安装态不再依赖当前工作目录碰巧位于仓库根

## 验证与发布闸门
- 日常快检：`bash scripts/validate_workspace.sh`（默认执行后端 fast gate、运行态 smoke tests、前端构建、bundle 报告与 coverage 报告；后端 coverage 可通过 `BACKEND_COVERAGE_FAIL_UNDER` 升级为阻断闸门，前端 coverage 默认非阻断，可通过 `STRICT_FRONTEND_COVERAGE=1` 提升为阻断）
- 后端全量发布闸门：`ENABLE_BACKEND_RELEASE_GATE=1 bash scripts/validate_workspace.sh` 或直接执行 `bash scripts/run_backend_release_gate.sh`
- 前端 bundle 预算阻断：`STRICT_FRONTEND_BUNDLE_BUDGET=1 FRONTEND_MAX_TOTAL_JS_KIB=800 FRONTEND_MAX_LARGEST_BUNDLE_KIB=550 bash scripts/validate_workspace.sh`
- 前端浏览器烟测统一入口：`bash scripts/run_frontend_e2e.sh`
- ROS2 launch 矩阵统一入口：`bash scripts/run_launch_test_matrix.sh`
- ROS2/Humble 发布闸门：`ENABLE_ROS_RELEASE_GATE=1 bash scripts/validate_workspace.sh`
- ROS2 发布前统一环境预检：`python3 scripts/ros_release_gate_preflight.py --workspace-root . --require-colcon --require-frontend-dist`
- CI 额外提供独立 `ros_release_gate` 作业，使用 ROS 2 Humble 容器先构建前端 release 产物，再执行 `colcon build/test`，并通过 `run_launch_test_matrix.sh` 执行全部 launch tests。
- ROS2 发布闸门要求在已安装 `colcon` 的 Humble 环境中执行，并补充 `colcon build` / `colcon test` 验证；显式开启后若环境不满足将直接失败。
- `validate_ros_workspace.sh` 与 `run_ros2_humble_runtime_validation.sh` 现在共享 `ros_release_gate_preflight.py`，统一检查 Ubuntu 22.04 / ROS2 Humble / Python 3.10+ / Node 20/22 / colcon / frontend dist / install setup 等前置条件。
- 进入 ROS 发布/运行态校验时会显式导出 `INSPECTION_REQUIRE_TYPED_INTERFACES=1`，并执行 `scripts/run_ros_typed_interface_import_smoke.sh`；typed ROS 接口若未正确生成，不再允许被节点内部的 ImportError 兼容分支静默掩盖。

## 说明
本工程优先保证主线闭环、trace 对齐、可追溯、可诊断与后续平台化扩展。视觉算法仍采用规则路线，但已具备进一步插件化与回放回归增强的骨架。下一步可在不推翻架构的前提下继续接入真实 STM32 协议、更多 detector 与更完整的 launch / rosbag2 / diagnostics 工具链。


## 前后端整合说明
- 前端源码已整合至 `frontend/`
- 新增 `inspection_hmi_gateway` 提供 HTTP / WebSocket 网关
- 详细说明见 `README_FULLSTACK.md`


## 验证报告约定
- `.artifacts/verification/verification_manifest.json` 是当前验证真值源。
- `.artifacts/verification/FINAL_VERIFICATION.md/.json`、`.artifacts/verification/backend_coverage.json` 与 `.artifacts/verification/logs/status.tsv` 属于自动生成产物；其中 `FINAL_VERIFICATION.*` 仅保留为兼容性/人工阅读输出，不再作为发布真值源。
- release/CI 模式下会强制要求 provenance 完整（`GIT_SHA` + `BUILD_ID/ci run id`）；本地开发态允许缺省，但 manifest 会明确标记 `provenanceComplete=false`。
- 实际 bringup 入口现在同时由本地 import smoke 与 ROS launch 解析测试覆盖，用于拦截相对导入、资源默认路径和 entrypoint 解析回归。
- 报告必须和当前 commit / 构建元数据一起阅读，不能把仓库中历史残留的验证文档当作脱离代码版本的长期事实。

## 配方激活语义
- `POST /api/v1/recipes/{recipe_id}/activate` 当前明确采用 **NEXT_RUN** 语义：控制面立即切换默认配方，但运行面以“下一次启动任务生效”为准；`/station/start` 在发起前会执行 recipe preflight 校验，首个带匹配 `recipe_id` 的运行结果会把 activation state 推进到 `RUNTIME_ACKNOWLEDGED`。
- 网关快照会同时暴露 `activeRecipeVersion`、`activeRecipeGeneration` 与 `recipeActivationState`，用于区分“已切换控制面”“已请求启动”与“运行链已确认当前配方”。

## 上位机 / STM32 / ESP32-S3 拆分运行说明
- 上位机仍是当前 `upper_computer/` 工作区，负责 ROS2 状态机、视觉处理、网关、日志与配方。
- STM32 通过 `station_bridge` 串口协议接入，推荐使用 `config/station/station_stm32.yaml`。
- ESP32-S3 通过 HTTP JPEG snapshot + health endpoint 接入，推荐使用 `config/camera/camera_esp32s3.yaml`。
- 接入真实硬件时的推荐命令：
```bash
ros2 launch inspection_bringup real_station.launch.py \
  sim_mode:=false \
  station_config_path:=config/station/station_stm32.yaml \
  camera_config_path:=config/camera/camera_esp32s3.yaml \
  profile_name:=production
```
- 当前上位机支持三类采集源：`mock`、本地 `OpenCV` 相机、`esp32_http`。
- `real_station.launch.py` 现在会把物化后的 `profile_config_path` 显式下发到 decision / vision / logger，避免 source/install 安装态 profile 解析分叉。
- 布尔 launch 参数通过显式类型转换传给节点，避免 `"false"` 在 Python 中被误判为真值。
- 若使用 `esp32_http` 采集源，可在 `config/camera/camera_esp32s3.yaml` 中配置 `esp32_auth_header / esp32_auth_token` 对接固件鉴权。

- 如果使用 `real_station.launch.py` 做模拟演示，必须显式传 `sim_mode:=true`；在 real mode 下若解析到 `camera.yaml` 或 `station.yaml`，launch 会直接失败而不是静默退回模拟配置。
