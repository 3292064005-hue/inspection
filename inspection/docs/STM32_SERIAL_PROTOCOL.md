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
