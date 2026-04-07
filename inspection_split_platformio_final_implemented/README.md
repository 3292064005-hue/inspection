# Inspection Workspace Split Delivery

本交付件把原桌面质检项目拆成三部分：

- `upper_computer/`：原 ROS2 + 网关 + 前端上位机工程
- `firmware/stm32_station_platformio/`：STM32 工位控制固件（PlatformIO）
- `firmware/esp32s3_camera_platformio/`：ESP32-S3 无线相机固件（PlatformIO）

## 目录职责

### 1. 上位机
负责：
- Supervisor / Orchestrator / FSM 控制平面
- 视觉采集、处理、决策、日志、结果归档
- HMI 网关与前端
- 与 STM32 串口协议对接
- 与 ESP32-S3 HTTP snapshot/health 接口对接

### 2. STM32 固件
负责：
- 接收上位机的 `feed / sort / reset / heartbeat / capability query`
- 返回 `ACK / POSITION_READY / SORT_DONE / HEARTBEAT / CAPABILITIES / FAULT`
- 驱动送料 / 分拣执行器与到位 / 故障输入

### 3. ESP32-S3 固件
负责：
- 提供 Wi-Fi 摄像头采集能力
- 对上位机暴露 JPEG snapshot 与 health endpoint
- 作为 `vision_acquisition` 的无线图像源

## 推荐运行命令

```bash
cd upper_computer
bash scripts/build_frontend.sh real
colcon build
source install/setup.bash
ros2 launch inspection_bringup real_station.launch.py profile_name:=production
```

## 发布治理与打包
- 顶层 split delivery 发布清单：`release/split_release_manifest.yaml`
- 顶层 CI：`.github/workflows/split_delivery_ci.yml`
- 纯源码打包脚本：`scripts/build_source_package.sh`
- 交付打包脚本：`scripts/build_release_bundle.sh`
- 分拆环境预检：`python3 scripts/validate_split_environment.py --workspace-root . --mode ci --require-node`

## 说明
- 当前上位机默认仍保留 mock / sim 路径，不会破坏原有联调方式。
- 当前 PlatformIO 工程已按原项目真实接口与调用链拆分，但本沙箱内没有 PlatformIO/ROS2 Humble 目标环境，因此**不能把 MCU 编译与 ROS 实机联调伪装成已实测通过**。
- ESP32-S3 固件默认要求通过 `X-Inspection-Token`（可配置）访问 HTTP API；若要兼容匿名访问，必须显式开启 `INSPECTION_ALLOW_ANONYMOUS_HTTP=1`。

- `sim_stack.launch.py` 是规范的模拟整栈入口；`real_station.launch.py` 现在默认绑定真实工位配置，并在 real mode 解析到 `camera.yaml` / `station.yaml` 时直接失败。
