# STM32 Station Firmware (PlatformIO)

## 目标职责
- 接收上位机 `station_bridge` 下发的 `feed / sort / reset / heartbeat / capability query`
- 返回 `ACK / POSITION_READY / SORT_DONE / HEARTBEAT / CAPABILITIES / FAULT`

## 默认板级映射（BluePill 示例）
- USART1 TX/RX：PA9 / PA10
- Feed：PB12
- Sort OK：PB13
- Sort NG：PB14
- Sort RECHECK：PB15
- Position sensor：PA8
- Fault input：PA11
- LED：PC13

## 关键配置
- 板级引脚：`firmware/stm32_station_platformio/include/inspection_station_config.h`
- PlatformIO 工程：`firmware/stm32_station_platformio/platformio.ini`
- runtime policy lib：`firmware/stm32_station_platformio/lib/inspection_station_runtime/inspection_station_runtime.hpp`

## 常用命令
```bash
pio run
pio test -e native
```

## 说明
- 默认引脚映射仅为示例，不等于真实控制柜接线。
- 若实际板级不同，先改配置再编译或烧录。
