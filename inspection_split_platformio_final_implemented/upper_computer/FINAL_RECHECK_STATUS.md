# Final Recheck Status

> **历史说明**：本文件是人工摘要，不是发布真值源。当前发布判断请以 `.artifacts/verification/verification_manifest.json` 与对应日志为准。

## 当前状态
- 发布验证真值源已收敛到 `.artifacts/verification/verification_manifest.json`。
- `FINAL_VERIFICATION.*` 保留为自动生成的兼容性/人工阅读产物，不再作为发布事实源。
- Backend required gate 现在采用分层前置：`check_python_syntax.py` → `run_backend_import_smoke_tests.sh` → required pytest suites。
- Backend release gate 现在复用同一前置链路，并在其后执行 `python3 -m pytest src/inspection_tests`，避免全量回归绕过低层语法/导入/运行时问题。
- Result detail 查询契约已稳定：`get_result()` 始终返回 `traceBundle`，查询侧 refresh 只影响新鲜度，不再改变返回结构。
- 控制面 typed/legacy 契约已收敛：`ControlCommand.msg` 正式包含 `payload_json`，typed message 生成/解析统一走 `inspection_utils.transport_contracts`。

## 当前容器内可复现验证
- `python3 scripts/check_python_syntax.py`
- `bash scripts/run_backend_required_tests.sh`
- `bash scripts/run_backend_runtime_smoke_tests.sh`
- `bash scripts/run_backend_release_gate.sh`
- `npm --prefix frontend test`

> 这些命令的最新结论请以 `.artifacts/verification/verification_manifest.json` 与 `.artifacts/verification/logs/*.log` 为准，不在本文件中重复固化具体通过数量，避免再次出现“文档数字滞后于代码真实状态”。

## 仍依赖外部环境的验证
- Ubuntu 22.04 + ROS2 Humble + colcon 的完整 build / launch / runtime 验证。
- 启用 Chromium/Playwright 的前端浏览器烟测。
- HIL / SIL / FIT 等依赖真实硬件或专用测试床的验证。
