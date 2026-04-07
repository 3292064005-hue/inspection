# 变更代码全量深度复核结论（复核后）

- 复核范围：P0 / P1 / P2 方案项、受影响代码文件、调用链、测试、CI、README/文档。
- 复核顺序：方案项 → 代码实现 → 调用链影响 → 边界行为 → 兼容性 → 环境一致性。
- 复核后新增修复：
  1. `src/inspection_bringup/setup.py` 修复安装态 `config/` 与 `docs/` 打包来源，避免 `bringup_share/config/...` 缺失。
  2. `src/inspection_hmi_gateway/.../server/context.py` 将 Action Job 注册失败从静默吞掉改为显式日志 + 审计事件。
  3. `src/inspection_hmi_gateway/.../server/main.py` 将 WebSocket 主循环异常从静默断连改为显式日志。
  4. `src/inspection_hmi_gateway/action_job_service.py` 将 transport 缺失/异常转为显式审计事件，再回退到兼容路径。
  5. `pytest.ini` / `scripts/validate_workspace.sh` / `.github/workflows/ci.yml` 重构验证入口：后端 required suites 阻塞、coverage 非阻塞、CI 增加独立 ROS Humble release gate 与 runtime validation。

- 本地复核证据：
  - `python -m py_compile $(find src scripts -name '*.py')`
  - `python -m pytest src/inspection_tests`
  - 结果：185 tests passed
