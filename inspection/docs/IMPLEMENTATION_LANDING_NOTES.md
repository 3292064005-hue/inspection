# 已确认方案代码落地说明

本文记录 P0/P1/P2 方案的代码级落地边界、迁移路径与回滚方式。

## P0 发布闭环

- `scripts/render_split_release_manifest.py` 区分 `source_delivery` 与 `formal_runnable_release`。
- formal release 必须具备 strict runtime evidence 与 `upper_computer/frontend/dist/index.html`。
- `upper_computer/scripts/validate_frontend_release.sh` 负责前端 install/test/typecheck/lint/build 验证。

## P1 命令面与动作语义

- `POST /api/v1/recipes/{recipe_id}/activate` 已降级为兼容重定向，不再直接写 recipe store。
- `switch_recipe_with_validation` 先执行 staged activation candidate validation，再提交激活；dry-run 不改变 active/default recipe。
- `run_benchmark` 降级为内部 synthetic QA tooling action，不进入默认 public catalog 或 public generated client。

## P2 治理与诊断分层

- 前端 mock action catalog 由 `action_registry.yaml` 派生生成，避免手写治理漂移。
- `topic_classification.yaml` 将 core release evidence topics 与 diagnostic/debug side channels 分离。
- legacy transport policy 增加 telemetry 与 removal-candidate 硬门槛。

## 迁移方式

1. 外部调用方从 direct recipe activation 迁移到 `/api/v1/actions/switch-recipe`。
2. 前端/SDK 重新生成 gateway contracts 后，不再使用 `activateRecipeDirect` 与 public `submitRunBenchmarkAction`。
3. 需要 benchmark 的 QA 工具应使用内部 action surface，并在报告中标记 synthetic。

## 回滚方式

- source delivery 通道保持可用；formal release 失败时不产出 runnable release。
- direct activation 可通过受控兼容分支短期恢复，但主干继续保持 action-plane-only。
- legacy transport 移除后仅通过 tagged hotfix branch 恢复，不在主干长期保留双路径。

## Finalized follow-up closures

- P1-03 is now fully internalized: `run_benchmark` is mounted only under `/api/internal/actions/run-benchmark`, excluded from public OpenAPI schema generation, and absent from public generated clients/catalogs. It remains available to maintainer/admin QA tooling through the canonical action job plane.
- P2-01 is closed by `upper_computer/scripts/generate_mock_action_catalog.py`; `frontend/src/mocks/generated/actionCatalog.ts` is generated from the runtime action registry and is checked by the backend contract tests.
- P2-02 is closed by `upper_computer/config/system/topic_classification.yaml`, runtime evidence validation, audit/manifest topic partitions, and logger artifact metadata. Diagnostic topics may be observed, but only configured core topics may populate `releaseTopics`.
- P2-03 is closed by typed-first transport policy fields for legacy telemetry, zero-usage release thresholds, release-note requirements, and tagged hotfix rollback strategy. Actual legacy publish enablement records telemetry when `INSPECTION_TRANSPORT_LEGACY_TELEMETRY_PATH` is configured.

