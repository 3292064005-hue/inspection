# Inspection Workspace

桌面视觉质检与自动分拣工作站的拆分交付仓库。仓库按三条主线组织：

- `upper_computer/`：ROS2 上位机、HMI Gateway、前端、日志、结果、配方与诊断。
- `firmware/stm32_station_platformio/`：STM32 工位执行固件，负责送料、到位、分拣、复位、心跳与能力查询。
- `firmware/esp32s3_camera_platformio/`：ESP32-S3 无线相机固件，提供 JPEG snapshot 与 health endpoint。

## 快速阅读顺序

1. `README.md`：仓库级总览、目录职责、运行入口与交付边界。
2. `docs/SPLIT_DEPLOYMENT.md`：拆分部署、发布验证、运行闭环矩阵与回滚边界。
3. `upper_computer/README.md`：上位机运行方式、验证入口、Gateway 契约与关键开关。
4. `upper_computer/docs/ARCHITECTURE.md`：主链闭环、typed transport 边界、资产权威源与治理策略。
5. 协议与固件说明：`docs/STM32_SERIAL_PROTOCOL.md`、`docs/ESP32S3_CAMERA_API.md`、两个固件目录下的 `README.md`。

## 文档路径规范

- 正式说明文档、配置中的 `documentationRefs` / `migration_guide`，以及文档相关测试断言，统一使用**仓库根相对路径**。
- 示例：`upper_computer/docs/ARCHITECTURE.md`、`docs/SPLIT_DEPLOYMENT.md`、`firmware/stm32_station_platformio/README.md`。
- 不再在正式说明中混用工作区相对路径，例如 `docs/ARCHITECTURE.md`、`config/system/...`、`frontend/...`、`src/...`。
- 命令中的 `cd upper_computer`、`python scripts/...` 属于执行上下文，不算文档路径引用。

## 推荐运行

当前默认交付物是**源码交付包**，不是预编译可运行包；`upper_computer/frontend/dist` 默认不随源码包分发。

```bash
cd upper_computer
bash scripts/build_frontend.sh real
colcon build
source install/setup.bash
ros2 launch inspection_bringup real_station.launch.py profile_name:=production
```

模拟栈入口：

```bash
cd upper_computer
ros2 launch inspection_bringup sim_stack.launch.py profile_name:=simulation
```

Simulation runtimes must use `station_capability_profile: simulation_station_default` so mock adapter expectations stay aligned with fail-closed station capability validation.

## 发布与验证入口

- 拆分交付 manifest：`release/split_release_manifest.yaml`
- 运行闭环矩阵：`release/runtime_validation_matrix.yaml`
- 环境预检：`python scripts/validate_split_environment.py --workspace-root . --mode ci --require-node`
- 目标环境 release 验证：`bash scripts/run_release_validation.sh`
- 源码打包：`bash scripts/build_source_package.sh`
- 正式交付打包：`bash scripts/build_release_bundle.sh`
- runtime matrix relaxed gate：`python scripts/run_runtime_validation_matrix.py --workspace-root . --skip-sim-execution --allow-missing-hardware-evidence`
- runtime matrix strict gate：`python scripts/run_runtime_validation_matrix.py --workspace-root . --strict-hardware-evidence`

`formal_runnable_release` 必须由 strict gate 触发，并完成前端 `npm ci / test / typecheck / lint / build:real` 与 `upper_computer/frontend/dist/index.html` 检查。

## Gateway 契约与生成资产

- 单一真值源：`upper_computer/config/system/action_registry.yaml`
- 派生资产：`upper_computer/config/system/action_capability_matrix.yaml`、`upper_computer/config/system/action_governance.yaml`、`upper_computer/config/system/compatibility_routes.yaml`、`upper_computer/config/system/station_capability_expectations.yaml`
- Gateway 派生资产：`upper_computer/frontend/openapi/inspection_gateway_openapi.json`、`upper_computer/frontend/src/shared/gateway/generated/actionApi.ts`
- 同步命令：`cd upper_computer && python scripts/sync_action_registry.py && python scripts/sync_gateway_contracts.py`
- drift 检查：`cd upper_computer && python scripts/sync_action_registry.py --check && python scripts/check_gateway_contract_drift.py`

## 运行边界

- `run_benchmark` 是内部 synthetic QA / 性能回归动作，不计入生产业务指标。
- `enable_annotated_image_diagnostics:=true|false` 控制 annotated 图像诊断订阅，默认 `false`。
- typed-first transport 为默认策略；legacy publish 只作为显式回滚能力保留。
- 只有设置 `INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED=1` 时，Gateway 才允许回退到本地 action runtime。
- 不要把 CI、静态检查或 relaxed gate 描述成真实硬件环境已完成正式交付验证。

## Release evidence closure rules

Formal runnable release eligibility is derived from strict runtime evidence, frontend dist presence, and generated manifest checks. Simulation evidence is written through `scripts/write_runtime_validation_evidence.py`; hardware evidence must use the same schema before `scripts/build_release_bundle.sh` can produce a formal bundle. Diagnostic ROS topics are retained for troubleshooting but are excluded from `releaseTopics` and cannot satisfy the core release evidence requirement.
