#pragma once

#include <cstdint>

#include "inspection_station_contract.hpp"

namespace inspection_station_runtime {

enum class ExecutionKind : std::uint8_t {
  NONE = 0,
  FEED = 1,
  SORT = 2,
};

inline bool command_busy(bool active) {
  return active;
}

inline const char* device_state(bool fault_latched, bool active, ExecutionKind kind) {
  if (fault_latched) {
    return "FAULT";
  }
  if (active && kind == ExecutionKind::FEED) {
    return "FEEDING";
  }
  if (active && kind == ExecutionKind::SORT) {
    return "SORTING";
  }
  return "READY";
}

inline bool sort_action_code_supported(int action_code) {
  return action_code >= 0 && inspection_station_contract::is_supported_action_code(static_cast<std::uint8_t>(action_code));
}

inline bool execution_ready(
    bool deadline_reached,
    ExecutionKind kind,
    bool wait_for_position_sensor,
    bool position_sensor_active) {
  if (deadline_reached) {
    return true;
  }
  return kind == ExecutionKind::FEED && wait_for_position_sensor && position_sensor_active;
}

}  // namespace inspection_station_runtime
