#include <cassert>
#include <string>
#include "inspection_camera_contract.hpp"

int main() {
  using namespace inspection_camera_contract;
  assert(auth_configured("abc"));
  assert(!auth_configured(""));
  assert(authorize_request("abc", "abc", false));
  assert(!authorize_request("", "abc", false));
  assert(authorize_request("", "", true));
  assert(degraded_reason(false, true, true) == std::string("wifi_disconnected"));
  assert(degraded_reason(true, false, true) == std::string("camera_unavailable"));
  assert(degraded_reason(true, true, false) == std::string("snapshot_failed"));
  assert(degraded_reason(true, true, true).empty());
  return 0;
}
