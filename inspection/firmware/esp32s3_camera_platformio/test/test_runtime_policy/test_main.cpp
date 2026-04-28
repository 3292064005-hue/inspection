#include <cassert>

#include "inspection_camera_runtime.hpp"

void setup() {
  using namespace inspection_camera_runtime;
  assert(wifi_credentials_configured("factory-ssid"));
  assert(should_reinitialize_camera(3, 3));
}

void loop() {}
