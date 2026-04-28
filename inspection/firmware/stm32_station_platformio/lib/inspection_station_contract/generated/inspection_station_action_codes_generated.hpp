#pragma once

#include <array>
#include <cstdint>

#ifndef INSPECTION_ACTION_CODE_SORT_OK
#define INSPECTION_ACTION_CODE_SORT_OK 1U
#endif

#ifndef INSPECTION_ACTION_CODE_SORT_NG
#define INSPECTION_ACTION_CODE_SORT_NG 2U
#endif

#ifndef INSPECTION_ACTION_CODE_SORT_RECHECK
#define INSPECTION_ACTION_CODE_SORT_RECHECK 3U
#endif

namespace inspection_station_generated {

inline constexpr std::array<std::uint8_t, 3> supported_action_codes() {
    return {
        static_cast<std::uint8_t>(INSPECTION_ACTION_CODE_SORT_OK),
        static_cast<std::uint8_t>(INSPECTION_ACTION_CODE_SORT_NG),
        static_cast<std::uint8_t>(INSPECTION_ACTION_CODE_SORT_RECHECK)
    };
}

}  // namespace inspection_station_generated
