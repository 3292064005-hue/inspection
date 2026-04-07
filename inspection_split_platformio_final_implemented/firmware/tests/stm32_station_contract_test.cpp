#include <cassert>
#include <vector>
#include "inspection_station_contract.hpp"

int main() {
  using namespace inspection_station_contract;
  const std::vector<std::uint8_t> payload{0x20U, 0x02U};
  auto encoded = encode_frame(0x10U, payload);
  Frame frame{};
  assert(decode_frame(encoded, frame));
  assert(frame.msg_type == 0x10U);
  assert(frame.payload == payload);
  encoded[3] ^= 0xFFU;
  assert(!decode_frame(encoded, frame));
  assert(is_supported_action_code(0x01U));
  assert(!is_supported_action_code(0x10U));
  return 0;
}
