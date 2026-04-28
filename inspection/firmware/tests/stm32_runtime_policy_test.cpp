#include <cassert>
#include <string>

#include "inspection_station_runtime.hpp"

int main() {
  using inspection_station_runtime::ExecutionKind;
  using namespace inspection_station_runtime;

  assert(command_busy(true));
  assert(!command_busy(false));
  assert(std::string(device_state(false, false, ExecutionKind::NONE)) == "READY");
  assert(std::string(device_state(false, true, ExecutionKind::FEED)) == "FEEDING");
  assert(std::string(device_state(false, true, ExecutionKind::SORT)) == "SORTING");
  assert(std::string(device_state(true, true, ExecutionKind::SORT)) == "FAULT");
  assert(sort_action_code_supported(1));
  assert(sort_action_code_supported(3));
  assert(!sort_action_code_supported(0));
  assert(!sort_action_code_supported(4));
  assert(execution_ready(true, ExecutionKind::SORT, false, false));
  assert(execution_ready(false, ExecutionKind::FEED, true, true));
  assert(!execution_ready(false, ExecutionKind::SORT, true, true));
  return 0;
}
