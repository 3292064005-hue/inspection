#pragma once

#include <cctype>
#include <string>

namespace inspection_json_payload {

inline std::size_t skip_ws(const std::string& json, std::size_t index) {
    while (index < json.size() && std::isspace(static_cast<unsigned char>(json[index])) != 0) {
        ++index;
    }
    return index;
}

inline std::size_t find_key(const std::string& json, const char* key) {
    const std::string marker = std::string("\"") + key + "\"";
    return json.find(marker);
}

inline bool locate_value(const std::string& json, const char* key, std::size_t& value_index) {
    const std::size_t key_pos = find_key(json, key);
    if (key_pos == std::string::npos) {
        return false;
    }
    const std::size_t colon = json.find(':', key_pos);
    if (colon == std::string::npos) {
        return false;
    }
    value_index = skip_ws(json, colon + 1);
    return value_index < json.size();
}

inline std::string extract_string(const std::string& json, const char* key, const char* fallback = "") {
    std::size_t value_index = 0;
    if (!locate_value(json, key, value_index) || json[value_index] != '"') {
        return fallback;
    }
    ++value_index;
    std::string output;
    output.reserve(16);
    bool escaping = false;
    for (; value_index < json.size(); ++value_index) {
        const char ch = json[value_index];
        if (escaping) {
            output.push_back(ch);
            escaping = false;
            continue;
        }
        if (ch == '\\') {
            escaping = true;
            continue;
        }
        if (ch == '"') {
            return output;
        }
        output.push_back(ch);
    }
    return fallback;
}

inline int extract_int(const std::string& json, const char* key, int fallback = 0) {
    std::size_t value_index = 0;
    if (!locate_value(json, key, value_index)) {
        return fallback;
    }
    int sign = 1;
    if (json[value_index] == '"') {
        ++value_index;
    }
    if (value_index < json.size() && json[value_index] == '-') {
        sign = -1;
        ++value_index;
    }
    int value = 0;
    bool seen = false;
    while (value_index < json.size() && json[value_index] >= '0' && json[value_index] <= '9') {
        seen = true;
        value = value * 10 + (json[value_index] - '0');
        ++value_index;
    }
    return seen ? sign * value : fallback;
}

}  // namespace inspection_json_payload
