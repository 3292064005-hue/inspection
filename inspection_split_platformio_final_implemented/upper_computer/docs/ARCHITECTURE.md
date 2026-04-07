# 架构说明

## V8 平台化分层
- **控制平面**：`inspection_supervisor` + `inspection_orchestrator` + `inspection_fsm`（Supervisor/FSM/Orchestrator 统一按 managed runtime 生命周期治理建模）
- **数据平面**：`vision_acquisition` + `vision_processing` + `inspection_decision`
- **设备平面**：`station_bridge`
- **质量平面**：`inspection_logger` + `inspection_diagnostics` + `inspection_tests`

## 主线闭环
`READY -> FEED_WAIT_ACK -> POSITION_WAIT -> CAPTURE_WAIT_FRAME -> ANALYZE_WAIT -> DECISION_WAIT -> SORT_WAIT_ACK -> SORT_WAIT_DONE -> COUNT_UPDATE -> READY`

## 新增系统级能力
- Supervisor：系统健康汇总、模式管理、启动顺序与恢复建议
- Orchestrator：系统级启动 / 自动运行 / 维护 / 恢复编排
- Diagnostics：桥接、视觉、故障、模式的统一健康快照
- Logger + Bag：trace 事件之外，支持可选 rosbag2 录制命令生成

## 设计原则
- 仅 FSM 拥有单件状态推进权
- 系统级模式切换交给 Supervisor / Orchestrator
- 视觉输出、决策输出、设备协议、诊断输出分层
- 所有关键结果落日志、图像证据与可回放记录
- 配方与 profile 分离，支持 production / debug / benchmark

## 生命周期治理约定
- FSM 规范节点名：`inspection_fsm_node`
- Orchestrator 规范节点名：`inspection_orchestrator_node`
- Supervisor 仅在生命周期命令成功排队后才推进内部派发记录，避免“未执行先记账”。
- 安装态资源解析与运行态可写目录解析分离，避免首次启动或目录尚不存在时回退到包目录。

## 配方控制面/运行面一致性
- HMI 网关中的 recipe activation 目前采用 **NEXT_RUN** 语义，并在 `/station/start` 前执行 recipe preflight 校验。
- `RecipeStore` 现在是兼容 façade；底层已拆成 `RecipeRepository`、`RecipeActivationService` 与 `RecipeRevisionArchive`，分别承担配方快照、激活生命周期与修订归档职责。
- 激活 receipt 仍会在 station `call_start()` 成功后把 activation state 从 `PENDING_START` 推进到 `START_REQUESTED`。
- Gateway snapshot 额外暴露 `activeRecipeVersion`、`activeRecipeGeneration` 与 `recipeActivationState`，避免把控制面切换误读成运行中热切换已完成；当结果链首次观察到匹配的 `recipe_id` 时，activation state 会推进到 `RUNTIME_ACKNOWLEDGED`。

## Read Model 热路径
- Logger 侧 `ReadModelWriter` 现在额外维护 `results/read_model_sync_state.json`，让查询侧能基于轻量 sync state 判断是否需要重建，而不是每次查询前全量扫描 trace 目录。
- 结果查询平面默认采用 projection-first / fail-closed：`fallback_legacy_reads` 在系统默认配置中已关闭，查询与 repair 通过显式状态面分离。
- 对单个 result/detail 的查询仍会在必要时做单 trace 对账刷新；该刷新会优先吸收当前 trace 作用域内可见的 events / artifacts / summary / manifest 证据，但当结构化证据尚未写到文件侧时，会保留 logger 已物化的 SQLite 热投影状态，避免查询侧刷新反向覆盖更热的 writer-side materialization。
- 查询过滤与 result/detail 组装已进一步从 `ReadModelRepository` 中抽离到 `read_model_result_queries.py`，将 SQL 过滤/分页与同步修复职责分层，降低查询热路径与同步治理逻辑的耦合。
- Read model 的 sync/readiness/refresh 决策已继续抽离到 `read_model_sync_coordinator.py`，projection rebuild 与单 trace refresh 的执行细节已抽离到 `read_model_projection_repair.py`；`ReadModelRepository` 现在主要保留策略编排、连接边界与查询入口。
- 网关新增 `GET /api/v1/results/read-model/status`，用于显式暴露 projection health / degraded mode / repairRequired，而不是依赖隐式 fallback 感知。
- bringup launch entrypoint 现在通过安装态 Python 模块共享 `sim_stack` builder，避免 `PythonLaunchDescriptionSource` 下的相对导入失败；`offline_replay` 与 logger profile snapshot 资源路径统一走绝对化解析。

## Typed Transport / ROS 接口约束
- `inspection_interfaces` 现在把 `ControlCommand` / `CaptureRequest` / `DiagnosticsSnapshot` / `SupervisorStateEnvelope` / `ActionExecutorEvent` 纳入正式 ROS message 生成列表。
- 进入 ROS 发布/运行态验证时会显式启用 `INSPECTION_REQUIRE_TYPED_INTERFACES=1`，核心节点会在启动期校验 typed 接口是否可导入；typed 接口缺失不再允许被业务节点内部的 ImportError 兼容分支静默掩盖。
- typed/legacy 双通道发布继续通过 `inspection_utils.transport_contracts` + `inspection_utils.transport_adapters` 向边界集中，业务节点内部不再各自重复拼装 canonical payload。
- `FSMNode` 已继续下沉为 ROS/lifecycle shell，运行时 ingress、egress 与 cycle metrics 分别下沉到 `fsm_ingress.py`、`fsm_egress.py`、`fsm_metrics.py`，减少状态机主类对消息解析、副作用发布和统计累积的耦合。
- 网关认证域继续拆分：`AuthService` 现在作为 façade，底层委托 `CredentialStore`、`SessionService`、`WsTicketService` 与 `BootstrapAdminService`，将用户配置装载、会话持久化、一次性 WebSocket ticket 与 bootstrap 管理边界拆开。

## 上位机 / STM32 / ESP32-S3 拆分约定
- 上位机：保留原有 ROS2 控制平面、数据平面、网关、日志与诊断能力。
- STM32：承担送料 / 到位 / 分拣 / 复位 / 心跳 / 能力查询，串口协议继续沿用 `inspection_utils.protocol` 的帧格式。
- ESP32-S3：承担无线图像采集，向上位机暴露 `/api/v1/camera/snapshot` 与 `/api/v1/camera/health`，上位机通过 `Esp32HttpCameraProvider` 轮询 JPEG snapshot。
- 推荐真实硬件配置文件：`config/station/station_stm32.yaml` + `config/camera/camera_esp32s3.yaml`。
