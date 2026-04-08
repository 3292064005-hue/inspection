# Repository Asset Status

本文件用于明确仓库内哪些资产是**主链有效资产**、哪些是**兼容保留资产**、哪些是**生成物/示例资产**，避免把历史快照误当成当前运行事实。

## A. 主链有效资产（运行/发布时直接消费）
- `config/camera/camera.yaml`
- `config/station/station.yaml`
- `config/recipes/*.yaml`
- `config/profiles/*.yaml`
- `config/compatibility/matrix.yaml`
- `config/system/diagnostic_actions.yaml`
- `src/inspection_bringup/launch/*.launch.py`
- `src/**/package.xml`
- `frontend/src/**`
- `frontend/package.json`
- `.github/workflows/ci.yml`
- `scripts/validate_workspace.sh`
- `scripts/validate_ros_workspace.sh`
- `scripts/run_ros2_humble_runtime_validation.sh`

## B. 兼容保留资产（仍可被旧链路/兼容逻辑消费，但不是唯一事实源）
- `src/inspection_bringup/launch/full_stack.launch.py`  
  历史 demo 入口，当前推荐显式使用 `sim_stack.launch.py` 或 `real_station.launch.py`。
- `config/system/system.yaml`  
  作为兼容系统级配置保留，但当前主运行链核心参数并不直接依赖它完成 profile 物化；禁止把它当作主链唯一事实源。
- `src/inspection_hmi_gateway/inspection_hmi_gateway/server/services.py`  
  兼容导出层；查询/命令实现已拆到 `query_services.py` 与 `command_services.py`。
- `src/inspection_hmi_gateway/inspection_hmi_gateway/server/query_services.py` / `command_services.py`  
  兼容导出层；动作/诊断主实现已下沉到 `server/operations/*`，结果查询/维护主实现已下沉到 `server/results/*`。

## C. 自动生成 / 示例 / 只读说明资产（不可当作脱离代码版本的长期事实）
- `.artifacts/verification/FINAL_VERIFICATION.md`
- `.artifacts/verification/FINAL_VERIFICATION.json`
- `.artifacts/verification/backend_coverage.json`
- `.artifacts/verification/logs/*`
- `IMPLEMENTATION_SUMMARY.md`
- `FINAL_RECHECK_STATUS.md`
- `REVIEW_RECHECK.md`
- `frontend/.env.example`
- `frontend/.env.demo`
- `frontend/.env.mock`

## 使用约束
1. 运行/发布问题优先看 A 类资产。
2. 若 B 类资产与 A 类资产冲突，以 A 类资产为准。
3. C 类资产必须结合当前 commit、CI 结果和生成时间阅读，禁止把旧报告当作当前系统事实。

4. 若需要判断“当前是否通过发布闸门”，只看 `.artifacts/verification/verification_manifest.json`，不要以历史总结 markdown 作为真值源。

- `src/vision_acquisition/vision_acquisition/provider_registry.py`
  相机 provider manifest 注册表；统一输出 provider 元数据目录。
- `src/inspection_utils/inspection_utils/plugin_contracts.py`
  provider / adapter / detector 共用插件元数据契约。


- `config/system/orchestrator.yaml`: authoritative orchestrator execution policy asset loaded by bringup launch files.
- `config/system/orchestrator_trees.yaml`: authoritative declarative behavior-tree catalog consumed by `inspection_orchestrator` runtime.
- `config/system/telemetry.yaml`: authoritative telemetry bridge catalog surfaced by gateway telemetry queries when no runtime snapshot is present.
