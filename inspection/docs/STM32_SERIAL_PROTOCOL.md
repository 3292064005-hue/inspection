# STM32 Serial Protocol

帧格式直接对齐上位机 `inspection_utils.protocol`：

```
STX(0x02) | CMD(1) | SEQ(1) | LEN(1) | PAYLOAD(N) | CRC8(1) | ETX(0x03)
```

## CRC
- 多项式：`0x07`
- 计算范围：`CMD + SEQ + LEN + PAYLOAD`

## 上位机下发的 payload
- `feed`：JSON，至少包含 `trace_id / batch_id / item_id`
- `sort`：JSON，至少包含 `trace_id / batch_id / item_id / action_code / target_bin / decision`
- `reset`：JSON，可包含 `fault_code / trace_id`

## STM32 回包 payload 约定
### ACK
```json
{"phase":"FEED|SORT|RESET","trace_id":"...","batch_id":"...","item_id":1}
```

### POSITION_READY
```json
{"trace_id":"...","batch_id":"...","item_id":1,"sensor_in_position":true}
```

### SORT_DONE
```json
{"trace_id":"...","batch_id":"...","item_id":1,"action_code":2,"target_bin":"NG"}
```

### CAPABILITIES
```json
{
  "protocol_version":"v1",
  "firmware_version":"stm32-station-pio-v1",
  "device_id":"stm32-station-01",
  "features":["SORT_ACK","HEARTBEAT","RESET_ACK","CAPABILITY_QUERY"]
}
```

- `CAPABILITIES` payload 现在同时返回 `supported_action_codes`，上位机能力注册表与工位桥配置可直接对齐。


## 命令 / 响应码语义
本文档以上位机 `upper_computer/src/inspection_utils/inspection_utils/protocol.py` 的常量定义为真值源；对接时应直接以代码常量为准，而不是手工复制数值。语义分组如下：
- 命令：`CMD_FEED_ONE`、`CMD_SORT_TO_BIN`、`CMD_RESET_FAULT`、`CMD_QUERY_CAPABILITIES`、`CMD_HEARTBEAT`
- 响应：`RSP_ACK`、`RSP_POSITION_READY`、`RSP_SORT_DONE`、`RSP_CAPABILITIES`、`RSP_HEARTBEAT`、`RSP_FAULT`

## 时序与异常语义
- 每帧由 `SEQ` 标识一次命令/响应往返；同一会话中应保持单调递增并允许按字节回绕。
- `ACK` 只表示设备已受理命令，不表示送料到位或分拣完成。
- `POSITION_READY` 表示待检件已到拍照位；`SORT_DONE` 表示执行机构完成本次分拣。
- 若上位机在约定超时内未收到 `ACK` / `POSITION_READY` / `SORT_DONE`，应按桥接层 watchdog 与重试策略进入故障或重连路径，而不是在协议层静默吞掉。
- 收到 `RSP_FAULT`、CRC 校验失败、ETX/STX 不完整或 `SEQ` 不匹配时，应视为无效帧或故障帧，由 `station_bridge` 触发 fail-closed 处理。

## Action capability profile
- `supported_action_codes` 以 `upper_computer/config/system/action_registry.yaml` 中的 `station_capability_profiles` 为真值源，并派生到 `upper_computer/config/station/station_stm32.yaml` 与 `firmware/stm32_station_platformio/lib/inspection_station_contract/generated/inspection_station_action_codes_generated.hpp`。
- action code 到 GPIO 的映射由 `firmware/stm32_station_platformio/include/inspection_station_action_profile.h` 派生，不再在 `main.cpp` 内扩散硬编码分支。


- `firmware/stm32_station_platformio/lib/inspection_station_contract/generated/inspection_station_capability_features_generated.hpp` 由 `upper_computer/scripts/sync_action_registry.py` 生成，作为 STM32 capabilities `features` 字段的唯一固件侧来源。


- `upper_computer/config/system/station_adapter_manifests.yaml` 由 `action_registry.yaml` 派生，约束 station adapter manifest 的 capability 元数据，避免 host/mock/firmware 对 capability 集合产生额外手写漂移。
