#pragma once

#include <array>
#include <cstdint>
#include <vector>

#include "generated/inspection_station_action_codes_generated.hpp"

namespace inspection_station_contract {

constexpr std::uint8_t STX = 0x02;
constexpr std::uint8_t ETX = 0x03;

struct Frame {
  std::uint8_t cmd{};
  std::uint8_t seq{};
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

inline std::vector<std::uint8_t> encode_frame(std::uint8_t cmd, std::uint8_t seq, const std::vector<std::uint8_t>& payload) {
  std::vector<std::uint8_t> frame{STX, cmd, seq, static_cast<std::uint8_t>(payload.size())};
  frame.insert(frame.end(), payload.begin(), payload.end());
  std::vector<std::uint8_t> crc_input{cmd, seq, static_cast<std::uint8_t>(payload.size())};
  crc_input.insert(crc_input.end(), payload.begin(), payload.end());
  frame.push_back(crc8(crc_input));
  frame.push_back(ETX);
  return frame;
}

inline bool decode_frame(const std::vector<std::uint8_t>& raw, Frame& out) {
  if (raw.size() < 6 || raw.front() != STX || raw.back() != ETX) return false;
  const auto cmd = raw[1];
  const auto seq = raw[2];
  const auto length = raw[3];
  if (raw.size() != static_cast<std::size_t>(length) + 6U) return false;
  std::vector<std::uint8_t> payload(raw.begin() + 4, raw.begin() + 4 + length);
  std::vector<std::uint8_t> crc_input{cmd, seq, length};
  crc_input.insert(crc_input.end(), payload.begin(), payload.end());
  if (crc8(crc_input) != raw[4 + length]) return false;
  out.cmd = cmd;
  out.seq = seq;
  out.payload = std::move(payload);
  return true;
}

inline constexpr auto supported_action_codes() {
  return inspection_station_generated::supported_action_codes();
}

inline bool is_supported_action_code(std::uint8_t action_code) {
  for (const auto code : supported_action_codes()) {
    if (code == action_code) {
      return true;
    }
  }
  return false;
}

}  // namespace inspection_station_contract
