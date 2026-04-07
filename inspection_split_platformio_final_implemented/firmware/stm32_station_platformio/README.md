# STM32 Station Firmware (PlatformIO)

## 目标职责
- 串口接收上位机 `station_bridge` 下发的 feed/sort/reset/heartbeat/query_capabilities
- 按原项目协议返回 ACK / POSITION_READY / SORT_DONE / HEARTBEAT / CAPABILITIES / FAULT

## 当前默认硬件映射（BluePill 示例）
- USART1 TX/RX: PA9 / PA10
- Feed: PB12
- Sort OK: PB13
- Sort NG: PB14
- Sort RECHECK: PB15
- Position sensor: PA8
- Fault input: PA11
- LED: PC13

## 注意
- 当前默认引脚映射是示例，不一定等于你的真实控制柜接线。
- 如果实际板级接线不同，先改 `include/inspection_station_config.h`。
