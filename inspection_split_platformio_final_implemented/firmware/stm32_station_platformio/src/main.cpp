#include "inspection_station_config.h"
#include "inspection_station_contract/inspection_station_contract.hpp"
#include "stm32f1xx_hal.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

namespace {
constexpr uint8_t STX = inspection_station_contract::STX;
constexpr uint8_t ETX = inspection_station_contract::ETX;
constexpr uint8_t CMD_FEED_ONE = 0x10;
constexpr uint8_t CMD_SORT_TO_BIN = 0x20;
constexpr uint8_t CMD_QUERY_STATUS = 0x30;
constexpr uint8_t CMD_RESET_FAULT = 0x40;
constexpr uint8_t CMD_QUERY_CAPABILITIES = 0x41;
constexpr uint8_t CMD_HEARTBEAT = 0x7E;

constexpr uint8_t RSP_ACK = 0x80;
constexpr uint8_t RSP_NACK = 0x81;
constexpr uint8_t RSP_POSITION_READY = 0x90;
constexpr uint8_t RSP_SORT_DONE = 0x91;
constexpr uint8_t RSP_HEARTBEAT = 0x92;
constexpr uint8_t RSP_CAPABILITIES = 0x93;
constexpr uint8_t RSP_FAULT = 0xE0;

UART_HandleTypeDef huart1{};

struct Frame {
    uint8_t cmd{0};
    uint8_t seq{0};
    std::string payload;
};

struct ActiveExecution {
    enum Kind : uint8_t { NONE = 0, FEED = 1, SORT = 2 } kind{NONE};
    enum Phase : uint8_t { IDLE = 0, PULSE_ASSERTED = 1, WAIT_COMPLETION = 2 } phase{IDLE};

    bool active{false};
    uint8_t seq{0};
    GPIO_TypeDef* pulse_port{nullptr};
    uint16_t pulse_pin{0};
    uint32_t pulse_deadline_ms{0};
    uint32_t completion_deadline_ms{0};
    bool wait_for_position_sensor{false};
    std::string trace_id;
    std::string batch_id;
    int item_id{-1};
    int action_code{0};
    std::string target_bin;
    std::string decision;
};

ActiveExecution g_execution{};
uint32_t g_last_heartbeat_ms = 0;
bool g_fault_latched = false;
char g_rx_byte = 0;
std::array<uint8_t, 512> g_stream{};
size_t g_stream_size = 0;

uint8_t crc8(const uint8_t* data, size_t size) {
    uint8_t crc = 0;
    for (size_t i = 0; i < size; ++i) {
        crc ^= data[i];
        for (uint8_t bit = 0; bit < 8; ++bit) {
            if (crc & 0x80) {
                crc = static_cast<uint8_t>(((crc << 1U) ^ 0x07U) & 0xFFU);
            } else {
                crc = static_cast<uint8_t>((crc << 1U) & 0xFFU);
            }
        }
    }
    return crc;
}

bool tick_reached(uint32_t now, uint32_t deadline) {
    return static_cast<int32_t>(now - deadline) >= 0;
}

/**
 * Build and send one framed protocol response over USART1.
 *
 * Args:
 *   cmd: Response command byte.
 *   seq: Correlation sequence echoed back to the upper computer.
 *   payload: JSON payload string.
 *
 * Returns:
 *   None.
 *
 * Raises:
 *   This function does not raise. UART write failures are intentionally not
 *   propagated because the firmware has no higher-level exception channel.
 *
 * Boundary behavior:
 *   Payloads longer than 255 bytes are truncated to preserve the protocol's
 *   one-byte length field.
 */
void send_frame(uint8_t cmd, uint8_t seq, const std::string& payload) {
    const uint8_t length = static_cast<uint8_t>(payload.size() > 255 ? 255 : payload.size());
    std::array<uint8_t, 260> buffer{};
    buffer[0] = STX;
    buffer[1] = cmd;
    buffer[2] = seq;
    buffer[3] = length;
    if (length > 0) {
        std::memcpy(buffer.data() + 4, payload.data(), length);
    }
    const uint8_t crc = crc8(buffer.data() + 1, static_cast<size_t>(3 + length));
    buffer[4 + length] = crc;
    buffer[5 + length] = ETX;
    HAL_UART_Transmit(&huart1, buffer.data(), static_cast<uint16_t>(6 + length), 100);
}

std::string json_escape(const std::string& value) {
    std::string out;
    out.reserve(value.size() + 8);
    for (char ch : value) {
        if (ch == '"' || ch == '\\') {
            out.push_back('\\');
        }
        out.push_back(ch);
    }
    return out;
}

std::string json_get_string(const std::string& json, const char* key, const char* fallback = "") {
    std::string marker = std::string("\"") + key + "\"";
    size_t key_pos = json.find(marker);
    if (key_pos == std::string::npos) {
        return fallback;
    }
    size_t colon = json.find(':', key_pos + marker.size());
    size_t start = json.find('"', colon + 1);
    if (colon == std::string::npos || start == std::string::npos) {
        return fallback;
    }
    size_t end = json.find('"', start + 1);
    if (end == std::string::npos) {
        return fallback;
    }
    return json.substr(start + 1, end - start - 1);
}

int json_get_int(const std::string& json, const char* key, int fallback = 0) {
    std::string marker = std::string("\"") + key + "\"";
    size_t key_pos = json.find(marker);
    if (key_pos == std::string::npos) {
        return fallback;
    }
    size_t colon = json.find(':', key_pos + marker.size());
    if (colon == std::string::npos) {
        return fallback;
    }
    size_t start = colon + 1;
    while (start < json.size() && (json[start] == ' ' || json[start] == '\t')) {
        ++start;
    }
    int sign = 1;
    if (start < json.size() && json[start] == '-') {
        sign = -1;
        ++start;
    }
    int value = 0;
    bool seen = false;
    while (start < json.size() && json[start] >= '0' && json[start] <= '9') {
        seen = true;
        value = value * 10 + (json[start] - '0');
        ++start;
    }
    return seen ? sign * value : fallback;
}

bool pin_active(GPIO_TypeDef* port, uint16_t pin, bool active_low) {
    GPIO_PinState state = HAL_GPIO_ReadPin(port, pin);
    if (active_low) {
        return state == GPIO_PIN_RESET;
    }
    return state == GPIO_PIN_SET;
}

void set_led(bool on) {
    HAL_GPIO_WritePin(INSPECTION_LED_GPIO, INSPECTION_LED_PIN, on ? GPIO_PIN_RESET : GPIO_PIN_SET);
}

void reset_actuator_outputs() {
    HAL_GPIO_WritePin(INSPECTION_FEED_GPIO, INSPECTION_FEED_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(INSPECTION_SORT_OK_GPIO, INSPECTION_SORT_OK_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(INSPECTION_SORT_NG_GPIO, INSPECTION_SORT_NG_PIN, GPIO_PIN_RESET);
    HAL_GPIO_WritePin(INSPECTION_SORT_RECHECK_GPIO, INSPECTION_SORT_RECHECK_PIN, GPIO_PIN_RESET);
}

void clear_execution() {
    reset_actuator_outputs();
    g_execution = {};
}

std::string device_state() {
    if (g_fault_latched) {
        return "FAULT";
    }
    if (g_execution.active && g_execution.kind == ActiveExecution::FEED) {
        return "FEEDING";
    }
    if (g_execution.active && g_execution.kind == ActiveExecution::SORT) {
        return "SORTING";
    }
    return "READY";
}

void send_fault(const char* fault_code, const char* message) {
    g_fault_latched = true;
    std::string payload = std::string("{\"fault_code\":\"") + json_escape(fault_code) +
        "\",\"message\":\"" + json_escape(message) +
        "\",\"device_id\":\"" + INSPECTION_DEVICE_ID + "\"}";
    send_frame(RSP_FAULT, 0, payload);
}

void send_capabilities(uint8_t seq) {
    std::string payload =
        std::string("{\"protocol_version\":\"") + INSPECTION_PROTOCOL_VERSION +
        "\",\"firmware_version\":\"" + INSPECTION_FW_VERSION +
        "\",\"device_id\":\"" + INSPECTION_DEVICE_ID +
        "\",\"features\":[\"SORT_ACK\",\"HEARTBEAT\",\"RESET_ACK\",\"CAPABILITY_QUERY\"]}";
    send_frame(RSP_CAPABILITIES, seq, payload);
}

void send_heartbeat(uint8_t seq) {
    char payload[192];
    std::snprintf(payload, sizeof(payload),
                  "{\"device_id\":\"%s\",\"firmware_version\":\"%s\",\"protocol_version\":\"%s\",\"uptime_ms\":%lu,\"station_state\":\"%s\"}",
                  INSPECTION_DEVICE_ID,
                  INSPECTION_FW_VERSION,
                  INSPECTION_PROTOCOL_VERSION,
                  static_cast<unsigned long>(HAL_GetTick()),
                  device_state().c_str());
    send_frame(RSP_HEARTBEAT, seq, payload);
}

void send_busy_nack(uint8_t seq) {
    send_frame(RSP_NACK, seq, "{\"fault_code\":\"FAULT_BUSY\",\"message\":\"command_in_progress\"}");
}

void start_pulse(GPIO_TypeDef* port, uint16_t pin, uint32_t pulse_ms) {
    HAL_GPIO_WritePin(port, pin, GPIO_PIN_SET);
    g_execution.pulse_port = port;
    g_execution.pulse_pin = pin;
    g_execution.pulse_deadline_ms = HAL_GetTick() + pulse_ms;
}

/**
 * Start one feed cycle without blocking the main control loop.
 *
 * Args:
 *   seq: Correlation sequence from the host command frame.
 *   payload: JSON payload associated with the feed request.
 *
 * Returns:
 *   None.
 *
 * Raises:
 *   No exception is raised.
 *
 * Boundary behavior:
 *   When another command is already executing, the request is rejected with a
 *   protocol NACK instead of stalling UART polling or fault handling.
 */
void start_feed_action(uint8_t seq, const std::string& payload) {
    if (g_execution.active) {
        send_busy_nack(seq);
        return;
    }
    g_execution = {};
    g_execution.active = true;
    g_execution.kind = ActiveExecution::FEED;
    g_execution.phase = ActiveExecution::PULSE_ASSERTED;
    g_execution.seq = seq;
    g_execution.trace_id = json_get_string(payload, "trace_id", "");
    g_execution.batch_id = json_get_string(payload, "batch_id", "");
    g_execution.item_id = json_get_int(payload, "item_id", -1);
    g_execution.wait_for_position_sensor = true;
    start_pulse(INSPECTION_FEED_GPIO, INSPECTION_FEED_PIN, INSPECTION_FEED_PULSE_MS);
}

bool resolve_sort_pin(int action_code, GPIO_TypeDef** port, uint16_t* pin) {
    if (!inspection_station_contract::is_supported_action_code(static_cast<uint8_t>(action_code))) {
        return false;
    }
    if (action_code == 1) {
        *port = INSPECTION_SORT_OK_GPIO;
        *pin = INSPECTION_SORT_OK_PIN;
        return true;
    }
    if (action_code == 2) {
        *port = INSPECTION_SORT_NG_GPIO;
        *pin = INSPECTION_SORT_NG_PIN;
        return true;
    }
    if (action_code == 3) {
        *port = INSPECTION_SORT_RECHECK_GPIO;
        *pin = INSPECTION_SORT_RECHECK_PIN;
        return true;
    }
    return false;
}

/**
 * Start one sort cycle without blocking the main control loop.
 *
 * Args:
 *   seq: Correlation sequence from the host command frame.
 *   payload: JSON payload associated with the sort request.
 *
 * Returns:
 *   None.
 *
 * Raises:
 *   No exception is raised.
 *
 * Boundary behavior:
 *   Unsupported action codes produce a deterministic NACK and do not alter the
 *   current actuator state.
 */
void start_sort_action(uint8_t seq, const std::string& payload) {
    if (g_execution.active) {
        send_busy_nack(seq);
        return;
    }
    const int action_code = json_get_int(payload, "action_code", 0);
    GPIO_TypeDef* pulse_port = nullptr;
    uint16_t pulse_pin = 0;
    if (!resolve_sort_pin(action_code, &pulse_port, &pulse_pin)) {
        send_frame(RSP_NACK, seq, "{\"fault_code\":\"FAULT_BAD_ACTION_CODE\"}");
        return;
    }
    g_execution = {};
    g_execution.active = true;
    g_execution.kind = ActiveExecution::SORT;
    g_execution.phase = ActiveExecution::PULSE_ASSERTED;
    g_execution.seq = seq;
    g_execution.trace_id = json_get_string(payload, "trace_id", "");
    g_execution.batch_id = json_get_string(payload, "batch_id", "");
    g_execution.item_id = json_get_int(payload, "item_id", -1);
    g_execution.action_code = action_code;
    g_execution.target_bin = json_get_string(payload, "target_bin", "");
    g_execution.decision = json_get_string(payload, "decision", "");
    start_pulse(pulse_port, pulse_pin, INSPECTION_SORT_PULSE_MS);
}

void process_reset(uint8_t seq) {
    g_fault_latched = false;
    clear_execution();
    set_led(false);
    send_frame(RSP_ACK, seq, "{\"phase\":\"RESET\",\"message\":\"reset_complete\"}");
}

void process_frame(const Frame& frame) {
    switch (frame.cmd) {
        case CMD_FEED_ONE:
            start_feed_action(frame.seq, frame.payload);
            break;
        case CMD_SORT_TO_BIN:
            start_sort_action(frame.seq, frame.payload);
            break;
        case CMD_RESET_FAULT:
            process_reset(frame.seq);
            break;
        case CMD_QUERY_CAPABILITIES:
            send_capabilities(frame.seq);
            break;
        case CMD_HEARTBEAT:
        case CMD_QUERY_STATUS:
            send_heartbeat(frame.seq);
            break;
        default:
            send_frame(RSP_NACK, frame.seq, "{\"fault_code\":\"FAULT_UNKNOWN_CMD\"}");
            break;
    }
}

bool try_parse_frame(Frame& frame) {
    if (g_stream_size < 5) {
        return false;
    }
    size_t start = 0;
    while (start < g_stream_size && g_stream[start] != STX) {
        ++start;
    }
    if (start > 0) {
        std::memmove(g_stream.data(), g_stream.data() + start, g_stream_size - start);
        g_stream_size -= start;
    }
    if (g_stream_size < 5 || g_stream[0] != STX) {
        return false;
    }
    const uint8_t length = g_stream[3];
    const size_t total = 1 + 3 + static_cast<size_t>(length) + 1 + 1;
    if (g_stream_size < total) {
        return false;
    }
    if (g_stream[total - 1] != ETX) {
        std::memmove(g_stream.data(), g_stream.data() + 1, g_stream_size - 1);
        --g_stream_size;
        return false;
    }
    const uint8_t expected_crc = crc8(g_stream.data() + 1, static_cast<size_t>(3 + length));
    const uint8_t actual_crc = g_stream[total - 2];
    if (expected_crc != actual_crc) {
        std::memmove(g_stream.data(), g_stream.data() + total, g_stream_size - total);
        g_stream_size -= total;
        return false;
    }
    frame.cmd = g_stream[1];
    frame.seq = g_stream[2];
    frame.payload.assign(reinterpret_cast<char*>(g_stream.data() + 4), length);
    std::memmove(g_stream.data(), g_stream.data() + total, g_stream_size - total);
    g_stream_size -= total;
    return true;
}

void poll_uart() {
    while (HAL_UART_Receive(&huart1, reinterpret_cast<uint8_t*>(&g_rx_byte), 1, 0) == HAL_OK) {
        if (g_stream_size < g_stream.size()) {
            g_stream[g_stream_size++] = static_cast<uint8_t>(g_rx_byte);
        } else {
            g_stream_size = 0;
        }
        Frame frame{};
        while (try_parse_frame(frame)) {
            process_frame(frame);
        }
    }
}

void send_feed_ack() {
    std::string ack = std::string("{\"phase\":\"FEED\",\"trace_id\":\"") + json_escape(g_execution.trace_id) +
        "\",\"batch_id\":\"" + json_escape(g_execution.batch_id) +
        "\",\"item_id\":" + std::to_string(g_execution.item_id) + "}";
    send_frame(RSP_ACK, g_execution.seq, ack);
}

void send_sort_ack() {
    std::string ack = std::string("{\"phase\":\"SORT\",\"trace_id\":\"") + json_escape(g_execution.trace_id) +
        "\",\"batch_id\":\"" + json_escape(g_execution.batch_id) +
        "\",\"item_id\":" + std::to_string(g_execution.item_id) +
        ",\"action_code\":" + std::to_string(g_execution.action_code) +
        ",\"target_bin\":\"" + json_escape(g_execution.target_bin) + "\"}";
    send_frame(RSP_ACK, g_execution.seq, ack);
}

void send_position_ready() {
    std::string payload = std::string("{\"trace_id\":\"") + json_escape(g_execution.trace_id) +
        "\",\"batch_id\":\"" + json_escape(g_execution.batch_id) +
        "\",\"item_id\":" + std::to_string(g_execution.item_id) +
        ",\"sensor_in_position\":true}";
    send_frame(RSP_POSITION_READY, g_execution.seq, payload);
}

void send_sort_done() {
    std::string payload = std::string("{\"trace_id\":\"") + json_escape(g_execution.trace_id) +
        "\",\"batch_id\":\"" + json_escape(g_execution.batch_id) +
        "\",\"item_id\":" + std::to_string(g_execution.item_id) +
        ",\"action_code\":" + std::to_string(g_execution.action_code) +
        ",\"target_bin\":\"" + json_escape(g_execution.target_bin) +
        "\",\"decision\":\"" + json_escape(g_execution.decision) + "\"}";
    send_frame(RSP_SORT_DONE, g_execution.seq, payload);
}

/**
 * Advance actuator execution without blocking UART, heartbeat, or fault paths.
 *
 * Args:
 *   None.
 *
 * Returns:
 *   None.
 *
 * Raises:
 *   No exception is raised.
 *
 * Boundary behavior:
 *   The function is safe to call every loop tick. It only changes state when
 *   pulse/completion deadlines are reached or the position sensor fires.
 */
void service_execution() {
    if (!g_execution.active) {
        return;
    }
    const uint32_t now = HAL_GetTick();
    if (g_execution.phase == ActiveExecution::PULSE_ASSERTED) {
        if (!tick_reached(now, g_execution.pulse_deadline_ms)) {
            return;
        }
        if (g_execution.pulse_port != nullptr && g_execution.pulse_pin != 0) {
            HAL_GPIO_WritePin(g_execution.pulse_port, g_execution.pulse_pin, GPIO_PIN_RESET);
        }
        if (g_execution.kind == ActiveExecution::FEED) {
            send_feed_ack();
            g_execution.completion_deadline_ms = now + INSPECTION_POSITION_DELAY_MS;
        } else if (g_execution.kind == ActiveExecution::SORT) {
            send_sort_ack();
            g_execution.completion_deadline_ms = now + INSPECTION_SORT_DONE_DELAY_MS;
        }
        g_execution.phase = ActiveExecution::WAIT_COMPLETION;
        return;
    }
    if (g_execution.phase != ActiveExecution::WAIT_COMPLETION) {
        return;
    }
    bool ready = tick_reached(now, g_execution.completion_deadline_ms);
    if (!ready && g_execution.kind == ActiveExecution::FEED && g_execution.wait_for_position_sensor) {
        ready = pin_active(INSPECTION_POSITION_SENSOR_GPIO, INSPECTION_POSITION_SENSOR_PIN, INSPECTION_POSITION_SENSOR_ACTIVE_LOW);
    }
    if (!ready) {
        return;
    }
    if (g_execution.kind == ActiveExecution::FEED) {
        send_position_ready();
    } else if (g_execution.kind == ActiveExecution::SORT) {
        send_sort_done();
    }
    clear_execution();
}

void service_fault_input() {
    const bool fault_active = pin_active(INSPECTION_FAULT_INPUT_GPIO, INSPECTION_FAULT_INPUT_PIN, INSPECTION_FAULT_INPUT_ACTIVE_LOW);
    if (fault_active && !g_fault_latched) {
        set_led(true);
        clear_execution();
        send_fault("FAULT_INPUT_ACTIVE", "fault input asserted");
    }
}

void service_periodic_heartbeat() {
    const uint32_t now = HAL_GetTick();
    if (now - g_last_heartbeat_ms >= INSPECTION_HEARTBEAT_INTERVAL_MS) {
        g_last_heartbeat_ms = now;
        send_heartbeat(0);
    }
}

void SystemClock_Config() {
    RCC_OscInitTypeDef RCC_OscInitStruct{};
    RCC_ClkInitTypeDef RCC_ClkInitStruct{};
    RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
    RCC_OscInitStruct.HSEState = RCC_HSE_ON;
    RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
    RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
    RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
    RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
    HAL_RCC_OscConfig(&RCC_OscInitStruct);

    RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                                  RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
    RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
    RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
    RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
    RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
    HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2);
}

void MX_USART1_UART_Init() {
    huart1.Instance = INSPECTION_UART_INSTANCE;
    huart1.Init.BaudRate = 115200;
    huart1.Init.WordLength = UART_WORDLENGTH_8B;
    huart1.Init.StopBits = UART_STOPBITS_1;
    huart1.Init.Parity = UART_PARITY_NONE;
    huart1.Init.Mode = UART_MODE_TX_RX;
    huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
    huart1.Init.OverSampling = UART_OVERSAMPLING_16;
    HAL_UART_Init(&huart1);
}

void MX_GPIO_Init() {
    __HAL_RCC_GPIOA_CLK_ENABLE();
    __HAL_RCC_GPIOB_CLK_ENABLE();
    __HAL_RCC_GPIOC_CLK_ENABLE();
    __HAL_RCC_USART1_CLK_ENABLE();

    GPIO_InitTypeDef gpio{};

    gpio.Pin = GPIO_PIN_9;
    gpio.Mode = GPIO_MODE_AF_PP;
    gpio.Speed = GPIO_SPEED_FREQ_HIGH;
    HAL_GPIO_Init(GPIOA, &gpio);

    gpio.Pin = GPIO_PIN_10;
    gpio.Mode = GPIO_MODE_INPUT;
    gpio.Pull = GPIO_NOPULL;
    HAL_GPIO_Init(GPIOA, &gpio);

    gpio.Pin = INSPECTION_LED_PIN;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(INSPECTION_LED_GPIO, &gpio);

    gpio.Pin = INSPECTION_FEED_PIN | INSPECTION_SORT_OK_PIN | INSPECTION_SORT_NG_PIN | INSPECTION_SORT_RECHECK_PIN;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init(GPIOB, &gpio);

    gpio.Pin = INSPECTION_POSITION_SENSOR_PIN | INSPECTION_FAULT_INPUT_PIN;
    gpio.Mode = GPIO_MODE_INPUT;
    gpio.Pull = GPIO_PULLUP;
    HAL_GPIO_Init(GPIOA, &gpio);

    reset_actuator_outputs();
    set_led(false);
}

}  // namespace

int main() {
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_USART1_UART_Init();

    send_capabilities(0);
    while (true) {
        poll_uart();
        service_execution();
        service_fault_input();
        service_periodic_heartbeat();
        HAL_Delay(2);
    }
}
