#include <cassert>
#include <string>

#include "inspection_json_payload.hpp"

int main() {
  using namespace inspection_json_payload;

  const std::string payload = R"({"trace_id":"trace-\"quoted\"","item_id":-7,"action_code":"3","target_bin":"OK_BIN"})";
  assert(extract_string(payload, "trace_id", "") == "trace-\"quoted\"");
  assert(extract_string(payload, "target_bin", "") == "OK_BIN");
  assert(extract_string(payload, "missing_key", "fallback") == "fallback");
  assert(extract_int(payload, "item_id", 0) == -7);
  assert(extract_int(payload, "action_code", 0) == 3);
  assert(extract_int("{\"action_code\":not-a-number}", "action_code", 9) == 9);
  return 0;
}
