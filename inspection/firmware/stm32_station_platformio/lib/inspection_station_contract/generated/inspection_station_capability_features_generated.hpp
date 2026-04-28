#pragma once

#include <array>

namespace inspection_station_generated {

inline constexpr std::array<const char*, 4> capability_features() {
    return {
        "SORT_ACK",
        "HEARTBEAT",
        "RESET_ACK",
        "CAPABILITY_QUERY"
    };
}

}  // namespace inspection_station_generated
