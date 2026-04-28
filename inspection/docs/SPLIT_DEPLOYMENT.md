# Split Deployment Guide

## 1. 交付组成
- `upper_computer/`：ROS2 主链、HMI Gateway、前端、日志/结果/配方与诊断
- `firmware/stm32_station_platformio/`：STM32 工位执行固件
- `firmware/esp32s3_camera_platformio/`：ESP32-S3 无线相机固件
- `release/`：版本与拆分交付 manifest、运行验证矩阵

## 2. 通信与部署边界

### 上位机 ↔ STM32
- 物理链路：USB CDC / UART
- 默认串口：`/dev/ttyUSB0`
- 默认波特率：`115200`
- 协议格式真值：`upper_computer/src/inspection_utils/inspection_utils/protocol.py`
- 关键命令：`CMD_FEED_ONE`、`CMD_SORT_TO_BIN`、`CMD_RESET_FAULT`、`CMD_QUERY_CAPABILITIES`、`CMD_HEARTBEAT`
- 关键响应：`RSP_ACK`、`RSP_POSITION_READY`、`RSP_SORT_DONE`、`RSP_HEARTBEAT`、`RSP_CAPABILITIES`、`RSP_FAULT`

### 上位机 ↔ ESP32-S3
- 物理链路：Wi-Fi / HTTP
- snapshot：`GET /api/v1/camera/snapshot`
- health：`GET /api/v1/camera/health`
- 上位机 provider：`Esp32HttpCameraProvider`

### 推荐配置文件
- STM32：`upper_computer/config/station/station_stm32.yaml`
- ESP32-S3：`upper_computer/config/camera/camera_esp32s3.yaml`

## 3. 发布与验证真值
- 版本源：`release/version_manifest.yaml`
- 拆分交付 manifest：`release/split_release_manifest.yaml`
- 运行闭环矩阵：`release/runtime_validation_matrix.yaml`
- release 验证入口：`scripts/run_release_validation.sh`
- matrix 门禁 / 执行器：`scripts/run_runtime_validation_matrix.py`
- evidence 根目录：`release/runtime_validation_evidence/`
- gate 真值：`release/runtime_validation_evidence/gate_status.json`（由 `run_runtime_validation_matrix.py` 生成）
- audit 派生产物：`release/runtime_validation_evidence/audit_summary.json`（只读展示，不得单独视为通过证明）

## 4. 运行闭环矩阵
当前矩阵定义四个最小闭环场景：
- `sim_closed_loop`
- `upper_computer_with_stm32`
- `upper_computer_with_esp32s3`
- `full_hardware_closed_loop`

执行规则：
- `sim_closed_loop`：允许在沙箱 / CI 环境执行，并由严格门禁把执行结果写入 `gate_status.json`
- 硬件场景：release 模式下要求显式 evidence JSON；没有证据时直接失败，不允许把“矩阵存在”写成“硬件已验证”
- `audit_summary.json` 必须与当前 matrix digest、strict gate status、evidence 文件一致；否则 formal release 打包失败

## 5. 推荐验证顺序
1. `python3 scripts/validate_split_environment.py --workspace-root . --mode ci`
2. `python3 scripts/validate_runtime_validation_matrix.py --workspace-root .`
3. `python3 scripts/render_split_release_manifest.py --workspace-root . --check`
4. `bash scripts/run_firmware_contract_tests.sh`
5. `cd upper_computer && bash scripts/run_backend_required_tests.sh`
6. `cd upper_computer && bash scripts/run_backend_runtime_smoke_tests.sh`
7. 在目标环境执行 `bash scripts/run_release_validation.sh`
8. 仅在内部开发/演示打包时使用 `bash scripts/build_release_bundle.sh --allow-unvalidated`；该模式会先生成 relaxed `gate_status.json`、派生 `audit_summary.json` 与最新 `split_release_manifest.yaml`，并输出 `internal_unvalidated` 发布物名；该产物会显式标记 `overallStatus: internal_unvalidated` / `formalReleaseEligible: false`，禁止当作正式交付件

## 6. 迁移与回滚边界

### Gateway 契约
- 迁移路径：OpenAPI → 生成前端契约 → canonical action plane
- 迁移完成后不再保留旧命令路由；HTTP 调用统一落到 `/api/v1/actions/*`

### Transport
- 迁移路径：typed 为核心、legacy 为边界桥接
- 回滚方式：保持 `upper_computer/config/system/transport_bridge_policy.yaml` 中 legacy publish 开启

### 动作治理
- 正式 / 兼容 / 实验动作都保留治理元数据
- 未满足 promotion 条件的动作不能被前端或验证报告伪装成正式能力

## 7. 安全与接口约束
- ESP32-S3 默认鉴权 Header：`X-Inspection-Token`
- 默认不允许匿名 HTTP；需要实验兼容模式时显式设置 `INSPECTION_ALLOW_ANONYMOUS_HTTP=1`
- 结果查询平面默认 projection-first / fail-closed；需要 repair 时使用 `POST /api/v1/results/read-model/repair`

## Runtime evidence bootstrap
- 先执行 `python3 scripts/bootstrap_runtime_validation_evidence.py --workspace-root .` 生成每个硬件场景的证据模板。
- 再把真实执行时间、操作人、commit、artifact 路径、expectedChecks 和 failureCriteria 结果填充到对应 JSON。
- `python3 scripts/run_runtime_validation_matrix.py --workspace-root . --strict-hardware-evidence` 会拒绝占位符模板和空 artifact 列表。


- Simulation runtimes must use `station_capability_profile: simulation_station_default` so mock adapter expectations stay aligned with fail-closed station capability validation.
