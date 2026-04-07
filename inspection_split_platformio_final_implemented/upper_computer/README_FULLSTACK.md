# Desktop Inspection Fullstack Workspace

## 环境与版本约束
- OS：Ubuntu 22.04 LTS
- ROS2：Humble Hawksbill
- Python：3.10+
- 前端 Node.js：20 LTS / 22 LTS
- FastAPI / Uvicorn 路径按当前工作区源码与 `requirements*.txt` 为准

## 运行要点

### 1. HMI 鉴权与首次启动
配置文件：`config/system/hmi_users.yaml`

- 仓库默认不再内置任何明文账号/口令。
- 若 `config/system/hmi_users.yaml` 为空，网关会在 `logs/runtime/bootstrap/bootstrap_admin.yaml` 生成一次性引导管理员。
- 可通过环境变量 `INSPECTION_HMI_BOOTSTRAP_USERNAME / INSPECTION_HMI_BOOTSTRAP_PASSWORD` 指定首次启动账号。
- 前端 `real` 模式默认关闭自动登录，登录后会先通过 `POST /api/v1/auth/ws-ticket` 换取短期 WebSocket 凭证。

### 1.1 资源路径与运行目录
- 配方、前端静态资源、用户库等只读资源默认从已安装包 share 目录解析。
- `INSPECTION_HMI_LOG_ROOT` 等运行目录会统一落到可写 runtime root，而不是按当前工作目录盲目拼接。
- 安装态默认 runtime root 优先级：`$INSPECTION_RUNTIME_ROOT` → `$ROS_HOME/inspection` → `${XDG_STATE_HOME:-~/.local/state}/inspection`。

### 2. 前端开发
```bash
cd frontend
npm ci
npm run dev:real
```

### 3. 前端构建
```bash
cd frontend
npm run build:real
# 或在仓库根执行统一脚本
bash scripts/build_frontend.sh real
```

### 4. 网关启动
```bash
export INSPECTION_HMI_PORT=8080
export INSPECTION_HMI_BOOTSTRAP_PASSWORD='ChangeMe#123'
export INSPECTION_HMI_REQUIRE_FRONTEND_DIST=1
ros2 run inspection_hmi_gateway inspection_hmi_gateway_server
```

- 发布模式下若 `frontend/dist/index.html` 缺失，网关会在启动期直接失败，而不是退化成“仅 API 存活”。

### 4.1 验证建议
```bash
bash scripts/validate_workspace.sh
# 默认执行后端 fast gate + 运行态 smoke tests + 前端构建 + coverage/bundle 报告
ENABLE_BACKEND_RELEASE_GATE=1 bash scripts/validate_workspace.sh
# 追加后端全量 pytest 发布闸门
STRICT_FRONTEND_BUNDLE_BUDGET=1 FRONTEND_MAX_TOTAL_JS_KIB=800 FRONTEND_MAX_LARGEST_BUNDLE_KIB=550 bash scripts/validate_workspace.sh
# 对 bundle 预算启用阻断式门禁
bash scripts/run_frontend_e2e.sh
# 前端 Playwright 浏览器烟测统一入口
ENABLE_ROS_RELEASE_GATE=1 bash scripts/validate_workspace.sh
# 在 Humble 环境中额外执行 colcon build/test 与 launch matrix 发布闸门
```

- 第一条用于源码快检与前后端验证，默认只执行后端 fast gate。
- 第二条用于追加后端全量 pytest 发布闸门。
- 第三条用于对前端 bundle 预算启用阻断式校验。
- 第四条用于显式执行前端浏览器烟测，要求已安装前端依赖与 Chromium。
- 第五条应在已安装 ROS2 Humble 与 `colcon` 的环境下执行，用于补充 `colcon build/test` 与 launch matrix 发布闸门；若环境不满足会直接失败。

### 5. 核心接口
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/session`
- `POST /api/v1/auth/ws-ticket`
- `GET /api/v1/station/snapshot`
- `GET /api/v1/results`
- `POST /api/v1/recipes/{recipe_id}/activate`（返回 `NEXT_RUN / PENDING_START` 语义的 activation receipt；`/station/start` 前做 recipe preflight，运行结果事件可推进到 `RUNTIME_ACKNOWLEDGED`）
- `POST /api/v1/exports/{batch_id}`
- `GET /api/v1/audit`
- `WS /ws/v1?ticket=...`

### 6. 运行态验证补充
- `validate_workspace.sh` 现在会额外执行 `scripts/run_backend_runtime_smoke_tests.sh`，用于拦截关键节点回调绑定/类作用域失配。
- `.artifacts/verification/verification_manifest.json` 是当前唯一的验证真值源；`FINAL_VERIFICATION.*` 仅作为兼容性/人工阅读产物保留。
- release/CI 模式下会强制要求 verification provenance 完整（`GIT_SHA` + `BUILD_ID/ci run id`）；本地开发态允许缺省，但 manifest 会明确标记 `provenanceComplete=false`。
- 进入 ROS 发布/运行态校验时会强制启用 typed interface import smoke（`INSPECTION_REQUIRE_TYPED_INTERFACES=1`），typed 接口缺失将被视为发布阻断。
- 结果查询平面默认采用 projection-first / fail-closed 策略；`fallback_legacy_reads` 仅在显式开启时允许回退到 legacy file scan。
- 网关额外提供 `GET /api/v1/results/read-model/status`，用于显式暴露 read-model projection 的健康与 repair 状态。
- bringup entrypoint 采用安装态可导入 builder（不再依赖 launch 目录内的相对导入），`offline_replay` 默认资源路径和 logger profile 快照路径均为绝对路径。
- 前端构建后会生成 `.artifacts/verification/frontend_bundle_report.json`，用于追踪 vendor chunk 体积，并支持通过 `STRICT_FRONTEND_BUNDLE_BUDGET=1` + `FRONTEND_MAX_TOTAL_JS_KIB/FRONTEND_MAX_LARGEST_BUNDLE_KIB` 升级为阻断。
