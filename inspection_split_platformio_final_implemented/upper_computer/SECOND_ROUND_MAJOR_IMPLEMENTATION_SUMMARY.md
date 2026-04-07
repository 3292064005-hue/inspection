# 第二轮 Major 项精确落地摘要

## 落地范围

### 后端
- `src/inspection_hmi_gateway/inspection_hmi_gateway/recipe_store.py`
- `src/inspection_hmi_gateway/inspection_hmi_gateway/app_facade.py`
- `src/inspection_hmi_gateway/inspection_hmi_gateway/runtime_components.py`
- `src/inspection_hmi_gateway/inspection_hmi_gateway/server/context.py`
- `src/inspection_tests/test_gateway_recipe_store.py`
- `src/inspection_tests/test_gateway_app_facade.py`

### 前端
- `frontend/src/widgets/__tests__/AuthGate.test.ts`
- `frontend/src/widgets/__tests__/ConnectionBanner.test.ts`
- `frontend/src/features/recipe-management/__tests__/useRecipeManagement.test.ts`
- `frontend/src/features/station-control/__tests__/useStationControl.test.ts`
- `frontend/src/shared/gateway/__tests__/safeGateway.test.ts`
- `frontend/src/shared/gateway/__tests__/service.test.ts`

### 文档
- `README.md`
- `README_FULLSTACK.md`
- `docs/ARCHITECTURE.md`

## 本轮实质性落地

1. **recipe start preflight**
   - 新增 `RecipeActivationError`
   - 新增 `preflight_start_request()`
   - 新增 `mark_activation_start_blocked()`
   - `call_start()` 在真正调用 `/inspection/start` 前先做 receipt/default snapshot/config generation 一致性校验

2. **runtime acknowledgement 闭环**
   - `GatewayReadModelProjector.on_result()` 新增 runtime result observation callback
   - `GatewayAppFacade.on_runtime_result_observed()` 在观察到匹配 `recipe_id` 的运行结果后将 activation state 推进到 `RUNTIME_ACKNOWLEDGED`
   - `RecipeStore.mark_runtime_acknowledged()` 持久化 runtime ack 元数据

3. **超时 / 依赖失败异常边界**
   - `GatewayAppFacade.call_start()` 对 preflight 失败、服务超时、服务不可用均给出明确 guidance
   - `GatewayAppFacade.reset_fault()` 在 reset service 不可用时显式回退控制话题复位并刷新 guidance
   - 新增专项测试覆盖这些路径

4. **前端 coverage 债务继续收口**
   - 新增网关包装层、service 单例、配方管理、登录门禁、连接横幅、工位控制等测试
   - 前端全局 coverage 现已超过 30% 阈值，可在 `STRICT_FRONTEND_COVERAGE=1` 下通过

## 验证命令

### 后端
- `python3 scripts/check_python_syntax.py`
- `pytest -q src/inspection_tests/test_gateway_recipe_store.py src/inspection_tests/test_gateway_app_facade.py src/inspection_tests/test_gateway_runtime_components.py src/inspection_tests/test_runtime_node_callback_contract.py`
- `bash scripts/run_backend_required_tests.sh`
- `bash scripts/run_backend_runtime_smoke_tests.sh`

### 前端
- `npm ci --prefer-offline --no-audit --progress=false`
- `npm test`
- `npm run typecheck`
- `npm run lint`
- `npm run build:real`
- `npm run coverage`
- `python3 scripts/report_frontend_bundle_sizes.py frontend/dist .artifacts/verification/frontend_bundle_report.json`

## 当前残留风险

1. ROS Humble release/runtime gate 仍需在真实 ROS 环境重跑；本轮沙箱未提供该环境。
2. recipe runtime ack 当前依赖**首个匹配 recipe_id 的运行结果事件**，不是 start service 返回体级 ack；这已经明显强于上一轮，但还不是最强协议形态。
3. 前端 coverage 虽已过闸，但页面级组件仍有较多未覆盖区域，后续可继续围绕 `bootstrap`、`diagnostics`、`pages` 做补测。
