# Inspection Workspace Split Delivery

本交付件把原桌面质检项目拆成三部分：

- `upper_computer/`：原 ROS2 + 网关 + 前端上位机工程
- `firmware/stm32_station_platformio/`：STM32 工位控制固件（PlatformIO）
- `firmware/esp32s3_camera_platformio/`：ESP32-S3 无线相机固件（PlatformIO）

## 目录职责

### 1. 上位机
负责：
- Supervisor / Orchestrator / FSM 控制平面
- 视觉采集、处理、决策、日志、结果归档
- HMI 网关与前端
- 与 STM32 串口协议对接
- 与 ESP32-S3 HTTP snapshot/health 接口对接

### 2. STM32 固件
负责：
- 接收上位机的 `feed / sort / reset / heartbeat / capability query`
- 返回 `ACK / POSITION_READY / SORT_DONE / HEARTBEAT / CAPABILITIES / FAULT`
- 驱动送料 / 分拣执行器与到位 / 故障输入

### 3. ESP32-S3 固件
负责：
- 提供 Wi-Fi 摄像头采集能力
- 对上位机暴露 JPEG snapshot 与 health endpoint
- 作为 `vision_acquisition` 的无线图像源

## 推荐运行命令

```bash
cd upper_computer
bash scripts/build_frontend.sh real
colcon build
source install/setup.bash
ros2 launch inspection_bringup real_station.launch.py profile_name:=production
```

## 发布治理与打包
- 顶层 split delivery 发布清单：`release/split_release_manifest.yaml`
- 顶层 CI：`.github/workflows/split_delivery_ci.yml`
- 纯源码打包脚本：`scripts/build_source_package.sh`
- 交付打包脚本：`scripts/build_release_bundle.sh`
- 分拆环境预检：`python3 scripts/validate_split_environment.py --workspace-root . --mode ci --require-node`
- 目标环境一键 release 验证：`bash scripts/run_release_validation.sh`

## 动作能力门禁
- `upper_computer` 当前对动作能力实行分级治理：
  - `run_calibration`：目录保留，但执行被显式阻断。
  - `run_benchmark`：synthetic / experimental，默认不可执行。
- 若确需启用 synthetic benchmark，必须显式设置：
  - `INSPECTION_EXPERIMENTAL_ACTIONS_ENABLED=1`
- 未设置该变量时，网关 API 会返回 `409 benchmark_requires_experimental_actions`，避免把实验动作误判为正式工艺能力。


## 维护模式 / 动作契约 / 工位桥运行时说明
- 维护模式不再由前端本地布尔值解锁危险动作；前端现在必须通过网关 `POST /api/v1/station/maintenance` 请求 supervisor 切换模式，并等待系统快照中的 `maintenance.enabled=true` 才允许执行诊断危险动作。诊断执行面同时切到标准 `/api/v1/actions/diagnostics/*` action job 提交链。
- `start_batch` 动作契约中的 `recipeId` / `batchId` 现在会真实进入运行链；不再存在“接口要求传 recipeId，但启动时忽略 payload”的漂移。
- `station_stm32.yaml` 中的 `adapter_name / protocol_version / supported_action_codes` 现在会进入 `station_bridge` 运行时：
  - `adapter_name` 决定具体 adapter factory 实例；
  - `protocol_version` 决定 bridge session 的协议版本；
  - `supported_action_codes` 会用于排序动作合法性校验，非法 action code 会直接触发 bridge fault，而不是静默下发。

## 观测 Topic 归宿
- `/inspection/camera/status` → diagnostics 聚合 + rosbag。
- `/inspection/result_raw` → diagnostics 聚合 + rosbag。
- `/inspection/image_annotated` → replay/rosbag；默认不启用 diagnostics 图像订阅，需显式开启 `enable_annotated_image_diagnostics:=true`。

## 说明
- 当前上位机默认仍保留 mock / sim 路径，不会破坏原有联调方式。
- 当前 PlatformIO 工程已按原项目真实接口与调用链拆分，但本沙箱内没有 PlatformIO/ROS2 Humble 目标环境，因此**不能把 MCU 编译与 ROS 实机联调伪装成已实测通过**。
- ESP32-S3 固件默认要求通过 `X-Inspection-Token`（可配置）访问 HTTP API；若要兼容匿名访问，必须显式开启 `INSPECTION_ALLOW_ANONYMOUS_HTTP=1`。

- `sim_stack.launch.py` 是规范的模拟整栈入口；`real_station.launch.py` 现在默认绑定真实工位配置，并在 real mode 解析到 `camera.yaml` / `station.yaml` 时直接失败。
- 结果/回放查询现在默认采用 projection-only / fail-closed；当 read model 过期时，HMI 需要先调用 `POST /api/v1/results/read-model/repair` 或执行离线 repair，再重试详情查询。
