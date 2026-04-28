#include <cassert>
#include <string>

#include "inspection_station_runtime.hpp"

void setup() {
  using inspection_station_runtime::ExecutionKind;
  using namespace inspection_station_runtime;
  assert(command_busy(true));
  assert(!command_busy(false));
  assert(std::string(device_state(false, false, ExecutionKind::NONE)) == "READY");
  assert(sort_action_code_supported(1));
}

void loop() {}
