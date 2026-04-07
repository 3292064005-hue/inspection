#pragma once

#include <string>

namespace inspection_camera_contract {

inline bool auth_configured(const std::string& token) {
  return !token.empty();
}

inline bool authorize_request(const std::string& provided_token, const std::string& configured_token, bool allow_anonymous) {
  if (allow_anonymous) return true;
  if (!auth_configured(configured_token)) return false;
  return !provided_token.empty() && provided_token == configured_token;
}

inline std::string degraded_reason(bool wifi_connected, bool camera_ok, bool last_snapshot_ok) {
  if (!wifi_connected) return "wifi_disconnected";
  if (!camera_ok) return "camera_unavailable";
  if (!last_snapshot_ok) return "snapshot_failed";
  return "";
}

}  // namespace inspection_camera_contract
