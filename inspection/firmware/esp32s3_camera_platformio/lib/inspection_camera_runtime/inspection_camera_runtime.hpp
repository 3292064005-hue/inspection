#pragma once

#include <cstdint>
#include <string>

#include "inspection_camera_contract.hpp"

namespace inspection_camera_runtime {

inline bool has_placeholder_value(const std::string& value) {
  return value.empty() || value == "__REPLACE_ME__" || value == "__REPLACE_WITH_TOKEN__";
}

inline bool wifi_credentials_configured(const std::string& ssid) {
  return !has_placeholder_value(ssid);
}

inline bool auth_token_configured(const std::string& token) {
  return inspection_camera_contract::auth_configured(token) && !has_placeholder_value(token);
}

inline bool request_authorized(
    const std::string& provided_token,
    const std::string& configured_token,
    bool allow_anonymous) {
  return inspection_camera_contract::authorize_request(provided_token, configured_token, allow_anonymous);
}

inline bool should_attempt_wifi_reconnect(
    std::uint32_t now_ms,
    std::uint32_t last_attempt_ms,
    std::uint32_t reconnect_interval_ms,
    bool wifi_configured,
    bool wifi_connected) {
  if (!wifi_configured || wifi_connected) {
    return false;
  }
  return now_ms - last_attempt_ms >= reconnect_interval_ms;
}

inline bool should_reinitialize_camera(int consecutive_failures, int threshold) {
  return threshold > 0 && consecutive_failures >= threshold;
}

}  // namespace inspection_camera_runtime
