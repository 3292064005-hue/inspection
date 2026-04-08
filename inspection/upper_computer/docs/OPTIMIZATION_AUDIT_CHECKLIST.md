# 优化方案逐项对照清单

## P0
- [x] 修复 processor_node 语法阻断
- [x] Python 逐文件语法闸门
- [x] 前端 lint 失败项清理
- [~] 文档与源码漂移治理（已引入自动验证报告，但整站联机验证仍依赖本机/CI）
- [x] trace / artifact / filename sanitize
- [x] 关闭开放式 /artifacts 暴露
- [x] 下线 localStorage 长期 bearer 主路径
- [x] session digest 落库
- [x] bootstrap admin 强制改密与失效
- [x] 补 processor_node 覆盖与导入验证

## P1
- [x] 受控生命周期运行层已接入，并在原生 ROS 环境自动升级为 `LifecycleNode`
- [x] supervisor 生命周期闭环已切到 native-compatible transition service 优先，topic fallback 仅作为桥接降级
- [~] orchestrator BT 骨架已落地
- [x] action 接口、网关异步 job、原生 ROS2 ActionServer/Client 已完成主链路接线
- [~] QoS 命名配置层已落地
- [~] station bridge 深度分层继续保留缺口
- [x] CameraProvider、重连诊断、发布节拍与陈旧帧健康监测已落地
- [~] decision trace 可解释化部分完成
- [~] artifact repository / evidence 模型部分完成
- [x] launch smoke、native lifecycle/qos、gateway/action executor validation 与自动发现 launch matrix 已接入运行矩阵

## P2/P3
- [x] MCAP 录制默认化并补入 writer config 接线
- [~] baseline / replay 回归部分完成
- [~] recipe revision / history 已有，schema migration / diff 未完成
- [~] 前端关键页面存在，任务中心/更深联调未完成
- [x] 导出任务异步化、可取消、可审计
- [x] 标准遥测桥配置与可达性探测已接入
- [x] Docker / devcontainer / pre-commit / editorconfig / CI / coverage gate 已补齐
- [~] Playwright smoke/e2e runner 已标准化，HIL/SIL/FIT 仍依赖外部设备与专门环境
- [ ] 多相机 / 多工位 / 监控报警 / 审批流未完成

## 当前结论
当前代码已经把控制面生命周期、Action 双向主链、相机健康诊断、launch matrix 与前端 e2e 门禁入口补到同一版状态；剩余缺口主要转移到更高阶能力与外部环境验证，而不再是当前仓库里的主链代码断层。
- [x] SQLite 连接显式关闭，`pytest` 不再依赖忽略 `ResourceWarning` 掩盖资源泄漏
- [x] native lifecycle dispatcher 会拒绝空 node，并对未知 transition 回退而不是伪造 transition id=0
- [x] ROS action bridge 已补必填 payload 校验与 job timeout 取消逻辑
- [x] `write_verification_report.py` 会 scrub 工作区绝对路径，减少环境漂移噪音
- [x] `run_launch_test_matrix.sh` 统一发现并执行全部 launch tests
- [x] `run_frontend_e2e.sh` 统一前端 Playwright 烟测入口与 Chromium 检测
