#pragma once

#include <cstdint>
#include <vector>

namespace inspection_station_contract {

constexpr std::uint8_t STX = 0x02;
constexpr std::uint8_t ETX = 0x03;

struct Frame {
  std::uint8_t msg_type{};
  std::vector<std::uint8_t> payload{};
};

inline std::uint8_t crc8(const std::vector<std::uint8_t>& data) {
  std::uint8_t crc = 0x00;
  for (std::uint8_t byte : data) {
    crc ^= byte;
    for (int i = 0; i < 8; ++i) {
      crc = (crc & 0x80U) ? static_cast<std::uint8_t>((crc << 1U) ^ 0x07U) : static_cast<std::uint8_t>(crc << 1U);
    }
  }
  return crc;
}

inline std::vector<std::uint8_t> encode_frame(std::uint8_t msg_type, const std::vector<std::uint8_t>& payload) {
  std::vector<std::uint8_t> frame{STX, msg_type, static_cast<std::uint8_t>(payload.size())};
  frame.insert(frame.end(), payload.begin(), payload.end());
  std::vector<std::uint8_t> crc_input{msg_type, static_cast<std::uint8_t>(payload.size())};
  crc_input.insert(crc_input.end(), payload.begin(), payload.end());
  frame.push_back(crc8(crc_input));
  frame.push_back(ETX);
  return frame;
}

inline bool decode_frame(const std::vector<std::uint8_t>& raw, Frame& out) {
  if (raw.size() < 5 || raw.front() != STX || raw.back() != ETX) return false;
  const auto msg_type = raw[1];
  const auto length = raw[2];
  if (raw.size() != static_cast<std::size_t>(length) + 5U) return false;
  std::vector<std::uint8_t> payload(raw.begin() + 3, raw.begin() + 3 + length);
  std::vector<std::uint8_t> crc_input{msg_type, length};
  crc_input.insert(crc_input.end(), payload.begin(), payload.end());
  if (crc8(crc_input) != raw[3 + length]) return false;
  out.msg_type = msg_type;
  out.payload = std::move(payload);
  return true;
}

inline bool is_supported_action_code(std::uint8_t action_code) {
  return action_code >= 0x01U && action_code <= 0x03U;
}

}  // namespace inspection_station_contract
