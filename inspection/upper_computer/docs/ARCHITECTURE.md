# 架构说明

## 目标与边界
本工作区负责桌面视觉质检与自动分拣系统的上位机部分，覆盖：
- ROS2 控制平面：Supervisor / Orchestrator / FSM
- 数据平面：采集 / 视觉处理 / 决策
- 设备平面：STM32 工位桥接、ESP32-S3 相机接入
- 质量平面：日志、结果投影、诊断与验证
- HMI 平面：HTTP / WebSocket 网关、前端契约、动作治理

不在本文件中重复阶段性整改记录、升级日志或审计过程；这里只描述**稳定结构、权威源与运行边界**。

文档中的文件引用统一使用**仓库根相对路径**，例如 `upper_computer/config/system/transport_bridge_policy.yaml`；不再混用工作区相对路径 `config/...`、`frontend/...`、`src/...`。

## 平台分层
- **控制平面**：`inspection_supervisor`、`inspection_orchestrator`、`inspection_fsm`
- **数据平面**：`vision_acquisition`、`vision_processing`、`inspection_decision`
- **设备平面**：`station_bridge`
- **质量平面**：`inspection_logger`、`inspection_diagnostics`、`inspection_tests`
- **HMI 平面**：`inspection_hmi_gateway`、`inspection_hmi`

## 主链闭环
主线状态推进由 FSM 独占：

`READY -> FEED_WAIT_ACK -> POSITION_WAIT -> CAPTURE_WAIT_FRAME -> ANALYZE_WAIT -> DECISION_WAIT -> SORT_WAIT_ACK -> SORT_WAIT_DONE -> COUNT_UPDATE -> READY`

约束：
1. 只有 FSM 可以推进单件状态。
2. 模式切换和恢复决策由 Supervisor / Orchestrator 管理。
3. 视觉输出、业务判定、设备协议与日志结果必须分层。
4. 结果与关键动作必须可追踪、可回放、可校验。

## 交付与运行边界
- 默认交付物是源码工作区，不包含 `upper_computer/frontend/dist`。
- Gateway 作为外部服务进程运行，不纳入 ROS2 lifecycle dispatch；是否强制 `frontend/dist` 存在由 `require_frontend_dist` / `INSPECTION_HMI_REQUIRE_FRONTEND_DIST` 显式控制。

## Gateway application boundary
`inspection_hmi_gateway.application_planes` 是网关业务边界的唯一组合根：
- `GatewayRecipePlane`：配方 CRUD、激活与版本切换
- `GatewayControlPlane`：start / stop / reset / maintenance / diagnostics
- `GatewayQueryPlane`：结果、批次、read-model 查询
- `GatewayProjectionPlane`：ROS runtime 事件到 gateway state / read model 的投影

`GatewayApplicationService` 是 Gateway 运行时唯一组合根；HTTP 路由和 websocket transport 统一依赖该 application service 暴露的 plane 组合，不再保留兼容 façade 或 `server/services.py`。

## Control-plane canonicalization
可执行动作入口统一收敛到 canonical action plane：`/api/v1/actions/*`。
旧的 `/api/v1/station/*` 与 `/api/v1/diagnostics/actions` 命令路由已删除；能力治理、审计、执行 transport 与 job 持久化统一走 canonical action plane。

## Typed transport boundary
系统默认以 typed ROS message 作为核心语义承载，legacy JSON 只保留在边界桥接：
- typed 消息定义：`inspection_interfaces`
- bridge 策略：`upper_computer/config/system/transport_bridge_policy.yaml`
- runtime event contract 与去重入口：`inspection_utils.runtime_event_contracts`
- legacy/typed bridge 适配入口：`inspection_utils.transport_adapters`

约束：
1. 核心业务节点消费 canonical payload，不在业务内部重复拼装 legacy JSON。
2. dual-publish 是否开启由 bridge policy 控制，而不是散落在节点逻辑中。
3. 进入 ROS 发布/运行态验证时，typed interface 缺失必须 fail-closed。

## Read-model boundary
结果查询面采用 projection-first / fail-closed，并与 runtime websocket 投影显式分层：
- 查询真值：materialized projection
- 显式维护入口：`POST /api/v1/results/read-model/repair`
- 状态查询入口：`GET /api/v1/results/read-model/status`

查询线程不负责隐式修复；repair、projection rebuild 与状态暴露分离，避免把查询副作用伪装成正常链路。在线 legacy file-scan fallback 已移除，仅保留显式 repair。`inspection_hmi_gateway.runtime_projection` 只负责 HMI runtime state / websocket 相关短生命周期投影，`inspection_logger` + SQLite materialized projection 才是结果查询与统计真值。

## Compatibility-route governance
兼容 HTTP 路由已从运行时与公开契约面完全移除。`upper_computer/config/system/compatibility_routes.yaml` 仅保留空 registry 快照用于审计，正式运行时不再解析 compatibility route 开关。

## Station protocol contract
工位串口协议契约由 `upper_computer/config/system/station_protocol_contract.yaml` 定义，约束：
- 可接受的 station 协议版本
- configured → reported 的允许组合
- 能力 payload 必填字段
- action code 校验策略

`station_bridge` 对 `CAPABILITIES`、`HEARTBEAT` 与 action code 采用 fail-closed 校验；设备不满足契约时不得完成握手。

## 上位机 / STM32 / ESP32-S3 拆分约定
- 上位机：控制平面、数据平面、HMI、日志与诊断
- STM32：送料 / 到位 / 分拣 / 复位 / 心跳 / 能力查询
- ESP32-S3：JPEG snapshot、health endpoint、无线图像源

推荐真实硬件配置：
- `upper_computer/config/station/station_stm32.yaml`
- `upper_computer/config/camera/camera_esp32s3.yaml`

## 资产权威源与文档收敛

### 主链有效资产
- `upper_computer/config/camera/camera.yaml`
- `upper_computer/config/station/station.yaml`
- `upper_computer/config/recipes/*.yaml`
- `upper_computer/config/profiles/*.yaml`
- `upper_computer/config/system/diagnostic_actions.yaml`
- `upper_computer/config/system/action_registry.yaml`
- `upper_computer/config/system/action_governance.yaml`
- `upper_computer/config/system/station_capability_expectations.yaml`
- `upper_computer/config/system/transport_bridge_policy.yaml`
- `upper_computer/src/inspection_bringup/launch/*.launch.py`
- `upper_computer/frontend/src/**`
- `upper_computer/frontend/package.json`
- `upper_computer/.github/workflows/ci.yml`
- `upper_computer/scripts/validate_workspace.sh`
- `upper_computer/scripts/validate_ros_workspace.sh`
- `upper_computer/scripts/run_ros2_humble_runtime_validation.sh`

### 兼容保留资产
- `upper_computer/config/system/system.yaml`：兼容系统配置，不是主链唯一事实源
- `upper_computer/src/inspection_hmi_gateway/inspection_hmi_gateway/server/query_services.py`
- `upper_computer/src/inspection_hmi_gateway/inspection_hmi_gateway/server/command_services.py`

### 自动生成与验证资产
- `.artifacts/verification/verification_manifest.json`：验证真值源
- `.artifacts/verification/backend_coverage.json`
- `.artifacts/verification/frontend_bundle_report.json`
- `upper_computer/src/inspection_bringup/launch/sim_stack.launch.py`：仿真闭环启动入口
- `.artifacts/verification/logs/*`
- `upper_computer/frontend/openapi/inspection_gateway_openapi.json`
- `upper_computer/frontend/src/shared/gateway/generated/actionApi.ts`

### 使用约束
1. 运行与发布问题优先看主链有效资产。
2. 兼容保留资产与主链冲突时，以主链有效资产为准。
3. 自动生成与验证资产必须结合当前 commit、CI 结果和生成时间阅读。
4. 不再保留独立的交付索引、升级说明、审计清单或模板 README 作为正式说明真值源。

## Topic 与 Action Registry 收敛
- Decision 节点只产出 `/inspection/decision_output`，FSM 负责把判定转成 `/station/sort_request`。
- `/station/sort_cmd` 仅作为迁移期 compatibility mirror，由 `publish_legacy_sort_cmd` 控制是否继续双发。
- legacy topic 默认关闭；仅在迁移回滚窗口内通过 `INSPECTION_TRANSPORT_LEGACY_ENABLED=1` 或按通道开关重新启用。
- Action 单一真值源收敛到 `upper_computer/config/system/action_registry.yaml`；OpenAPI、capability matrix、governance、compatibility route governance 与 STM32 capability expectation 均由该 registry 派生，且 station_bridge 握手期直接按派生 expectation 校验 station features / action codes。
- 运行拓扑与生命周期治理真值收敛到 `upper_computer/config/system/lifecycle_graph.yaml`；其中同时声明 lifecycle-managed 节点、supervisor-monitored 节点、故障域、criticality，以及 gateway / supervisor 的非 managed 边界；supervisor 启动顺序、必需节点集合、节点分级与治理矩阵均从该文件解析。
- `run_benchmark` 是内部 synthetic QA / 性能回归动作；默认公共目录和公共生成客户端不暴露该动作，其结果不得计入生产业务指标。
- `inspection.result.created` 仅保留为显式回滚兼容别名；默认不发出，只有设置 `INSPECTION_RESULT_CREATED_ALIAS_ENABLED=1` 才重新开启。第一方消费者与 mock 演示链已全部切换到 canonical 事件 `inspection.result.finalized`。
- `scripts/build_release_bundle.sh --allow-unvalidated` 不再留下“缺 gate status / manifest 过期”的半状态；它会生成 relaxed gate、派生 audit，并把 `split_release_manifest.yaml` 收敛到当前交付包真值，其中 `formalReleaseEligible` 必为 `false`。
- 统一动作执行链路默认 fail-closed；仅在显式设置 `INSPECTION_ACTION_LOCAL_RUNTIME_ENABLED=1` 时允许回滚到进程内执行运行时。


- Simulation runtimes must use `station_capability_profile: simulation_station_default` so mock adapter expectations stay aligned with fail-closed station capability validation.


- 兼容路由已删除；迁移调用方必须直接切换到 canonical action plane。

### Internal QA action and evidence boundaries

`run_benchmark` is an internal synthetic QA action. It is not part of the public `/api/v1/actions/*` route surface, public OpenAPI schema, generated public clients, or operator action catalog. It remains accessible only through the internal `/api/internal/actions/run-benchmark` namespace and the canonical action job executor.

Runtime release evidence is topic-classified. Core topics defined in `config/system/topic_classification.yaml` are the only topics that may satisfy formal `releaseTopics`; diagnostic/debug topics can be logged and audited but cannot be counted as release readiness proof.
