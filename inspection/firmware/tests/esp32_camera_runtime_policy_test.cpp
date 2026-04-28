#include <cassert>

#include "inspection_camera_runtime.hpp"

int main() {
  using namespace inspection_camera_runtime;

  assert(has_placeholder_value(""));
  assert(has_placeholder_value("__REPLACE_ME__"));
  assert(!has_placeholder_value("factory-ssid"));
  assert(wifi_credentials_configured("factory-ssid"));
  assert(!wifi_credentials_configured("__REPLACE_ME__"));
  assert(auth_token_configured("token-123"));
  assert(!auth_token_configured(""));
  assert(request_authorized("token-123", "token-123", false));
  assert(!request_authorized("", "token-123", false));
  assert(should_attempt_wifi_reconnect(5000, 1000, 3000, true, false));
  assert(!should_attempt_wifi_reconnect(2000, 1000, 3000, true, false));
  assert(!should_attempt_wifi_reconnect(5000, 1000, 3000, false, false));
  assert(!should_attempt_wifi_reconnect(5000, 1000, 3000, true, true));
  assert(should_reinitialize_camera(3, 3));
  assert(!should_reinitialize_camera(2, 3));
  return 0;
}
