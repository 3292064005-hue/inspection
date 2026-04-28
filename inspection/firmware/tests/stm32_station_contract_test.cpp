#include <cassert>
#include <cstdint>
#include <vector>

#include "inspection_station_contract.hpp"

int main() {
  using namespace inspection_station_contract;

  const std::vector<std::uint8_t> payload{0x10, 0x20, 0x30};
  auto frame = encode_frame(0x41, 0x07, payload);

  Frame decoded{};
  assert(decode_frame(frame, decoded));
  assert(decoded.cmd == 0x41);
  assert(decoded.seq == 0x07);
  assert(decoded.payload == payload);

  frame[4] ^= 0xFF;
  assert(!decode_frame(frame, decoded));

const auto supported_codes = supported_action_codes();
assert(supported_codes.size() == 3U);
assert(supported_codes[0] == 0x01U);
assert(supported_codes[2] == 0x03U);
assert(is_supported_action_code(0x01));
assert(is_supported_action_code(0x03));
assert(!is_supported_action_code(0x00));
assert(!is_supported_action_code(0x04));
  return 0;
}
