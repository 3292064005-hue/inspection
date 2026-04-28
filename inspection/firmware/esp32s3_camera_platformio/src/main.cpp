#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <WebServer.h>
#include <string>
#include "esp_camera.h"
#include "inspection_camera_config.h"
#include "inspection_camera_contract/inspection_camera_contract.hpp"
#include "inspection_camera_runtime.hpp"

namespace {
WebServer server(INSPECTION_HTTP_PORT);
uint32_t frames_served = 0;
uint32_t camera_failures = 0;
uint32_t wifi_reconnect_count = 0;
uint32_t camera_reinit_count = 0;
uint32_t boot_ms = 0;
uint32_t last_wifi_status_poll_ms = 0;
uint32_t last_wifi_reconnect_attempt_ms = 0;
uint8_t consecutive_snapshot_failures = 0;
bool camera_ok = false;
bool last_snapshot_ok = false;
bool camera_initialized = false;

camera_config_t buildCameraConfig() {
    CameraPinConfig pins = inspection_camera_pins();
    camera_config_t cfg{};
    cfg.ledc_channel = LEDC_CHANNEL_0;
    cfg.ledc_timer = LEDC_TIMER_0;
    cfg.pin_d0 = pins.d0;
    cfg.pin_d1 = pins.d1;
    cfg.pin_d2 = pins.d2;
    cfg.pin_d3 = pins.d3;
    cfg.pin_d4 = pins.d4;
    cfg.pin_d5 = pins.d5;
    cfg.pin_d6 = pins.d6;
    cfg.pin_d7 = pins.d7;
    cfg.pin_xclk = pins.xclk;
    cfg.pin_pclk = pins.pclk;
    cfg.pin_vsync = pins.vsync;
    cfg.pin_href = pins.href;
    cfg.pin_sccb_sda = pins.sda;
    cfg.pin_sccb_scl = pins.scl;
    cfg.pin_pwdn = pins.pwdn;
    cfg.pin_reset = pins.reset;
    cfg.xclk_freq_hz = 20000000;
    cfg.pixel_format = PIXFORMAT_JPEG;
    cfg.frame_size = static_cast<framesize_t>(INSPECTION_FRAME_SIZE);
    cfg.jpeg_quality = INSPECTION_JPEG_QUALITY;
    cfg.fb_count = psramFound() ? 2 : 1;
    cfg.fb_location = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
    cfg.grab_mode = CAMERA_GRAB_LATEST;
    return cfg;
}

String configuredWifiSsid() { return String(INSPECTION_WIFI_SSID); }
String configuredWifiPassword() { return String(INSPECTION_WIFI_PASSWORD); }
String configuredAuthToken() { return String(INSPECTION_HTTP_AUTH_TOKEN); }
String configuredAuthHeader() { return String(INSPECTION_HTTP_AUTH_HEADER); }

bool hasPlaceholderValue(const String& value) {
    return inspection_camera_runtime::has_placeholder_value(std::string(value.c_str()));
}

bool wifiCredentialsConfigured() {
    return inspection_camera_runtime::wifi_credentials_configured(std::string(configuredWifiSsid().c_str()));
}

bool authTokenConfigured() {
    const String token = configuredAuthToken();
    return inspection_camera_contract::auth_configured(std::string(token.c_str())) && !hasPlaceholderValue(token);
}

bool allowAnonymousHttp() {
    return INSPECTION_ALLOW_ANONYMOUS_HTTP != 0;
}

const char* degradedReason() {
    if (!wifiCredentialsConfigured()) {
        return "wifi_not_configured";
    }
    if (!allowAnonymousHttp() && !authTokenConfigured()) {
        return "http_auth_not_configured";
    }
    static std::string reason;
    reason = inspection_camera_contract::degraded_reason(WiFi.status() == WL_CONNECTED, camera_ok, last_snapshot_ok);
    return reason.empty() ? "none" : reason.c_str();
}

bool ensureAuthorized() {
    if (allowAnonymousHttp()) {
        return true;
    }
    if (!authTokenConfigured()) {
        server.send(503, "application/json", "{\"authorized\":false,\"reason\":\"http_auth_not_configured\"}");
        return false;
    }
    const String provided = server.hasHeader(configuredAuthHeader().c_str()) ? server.header(configuredAuthHeader()) : String();
    if (!inspection_camera_contract::authorize_request(std::string(provided.c_str()), std::string(configuredAuthToken().c_str()), false)) {
        server.sendHeader("WWW-Authenticate", "InspectionToken");
        const char* reason = provided.isEmpty() ? "missing_token" : "invalid_token";
        server.send(401, "application/json", String("{\"authorized\":false,\"reason\":\"") + reason + "\"}");
        return false;
    }
    return true;
}

bool connectWiFi(uint32_t timeout_ms = INSPECTION_WIFI_CONNECT_TIMEOUT_MS) {
    if (!wifiCredentialsConfigured()) {
        WiFi.disconnect(true, true);
        return false;
    }
    WiFi.mode(WIFI_STA);
    WiFi.begin(configuredWifiSsid().c_str(), configuredWifiPassword().c_str());
    const uint32_t start_ms = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start_ms) < timeout_ms) {
        delay(250);
    }
    return WiFi.status() == WL_CONNECTED;
}

bool setupCamera() {
    camera_config_t cfg = buildCameraConfig();
    const esp_err_t status = esp_camera_init(&cfg);
    camera_ok = (status == ESP_OK);
    camera_initialized = camera_ok;
    if (!camera_ok) {
        camera_failures++;
    }
    return camera_ok;
}

bool reinitializeCamera() {
    if (camera_initialized) {
        esp_camera_deinit();
        camera_initialized = false;
    }
    camera_reinit_count++;
    consecutive_snapshot_failures = 0;
    return setupCamera();
}

void serviceWiFi() {
    const uint32_t now = millis();
    if (now - last_wifi_status_poll_ms < INSPECTION_WIFI_STATUS_POLL_MS) {
        return;
    }
    last_wifi_status_poll_ms = now;
    if (WiFi.status() == WL_CONNECTED) {
        return;
    }
    if (!wifiCredentialsConfigured()) {
        return;
    }
    if (now - last_wifi_reconnect_attempt_ms < INSPECTION_WIFI_RECONNECT_INTERVAL_MS) {
        return;
    }
    last_wifi_reconnect_attempt_ms = now;
    wifi_reconnect_count++;
    connectWiFi();
}

/**
 * Publish current device health as JSON.
 *
 * Returns:
 *   HTTP 200 with the serialized health payload.
 *
 * Boundary behavior:
 *   Wi-Fi may be disconnected while the camera itself is healthy; both states
 *   are reported independently so the upper computer can distinguish transport
 *   failure from sensor failure.
 */
void handleHealth() {
    if (!ensureAuthorized()) {
        return;
    }
    StaticJsonDocument<768> doc;
    doc["deviceId"] = INSPECTION_DEVICE_ID;
    doc["firmwareVersion"] = INSPECTION_FW_VERSION;
    doc["cameraOk"] = camera_ok;
    doc["framesServed"] = frames_served;
    doc["cameraFailures"] = camera_failures;
    doc["wifiConnected"] = WiFi.status() == WL_CONNECTED;
    doc["wifiRssi"] = WiFi.isConnected() ? WiFi.RSSI() : -127;
    doc["wifiConfigured"] = wifiCredentialsConfigured();
    doc["reconnectCount"] = wifi_reconnect_count;
    doc["cameraReinitCount"] = camera_reinit_count;
    doc["lastSnapshotOk"] = last_snapshot_ok;
    doc["uptimeMs"] = millis() - boot_ms;
    doc["snapshotPath"] = "/api/v1/camera/snapshot";
    doc["healthPath"] = "/api/v1/camera/health";
    doc["authEnabled"] = !allowAnonymousHttp();
    doc["authHeader"] = !allowAnonymousHttp() ? configuredAuthHeader() : "";
    doc["degradedReason"] = degradedReason();
    String payload;
    serializeJson(doc, payload);
    server.send(200, "application/json", payload);
}

/**
 * Capture one JPEG frame and return it over HTTP.
 *
 * Returns:
 *   HTTP 200 with `image/jpeg` when a frame is captured successfully.
 *
 * Boundary behavior:
 *   Camera capture failure returns HTTP 503 instead of an empty body so the
 *   upper computer can classify the failure as transport-side degradation.
 */
void handleSnapshot() {
    if (!ensureAuthorized()) {
        return;
    }
    camera_fb_t* frame = esp_camera_fb_get();
    if (frame == nullptr) {
        camera_failures++;
        camera_ok = false;
        last_snapshot_ok = false;
        consecutive_snapshot_failures++;
        if (inspection_camera_runtime::should_reinitialize_camera(consecutive_snapshot_failures, INSPECTION_CAMERA_REINIT_FAILURE_THRESHOLD)) {
            const bool reinit_ok = reinitializeCamera();
            server.send(
                503,
                "application/json",
                reinit_ok
                    ? "{\"cameraOk\":false,\"reason\":\"capture_failed_reinitialized\"}"
                    : "{\"cameraOk\":false,\"reason\":\"capture_failed_reinit_failed\"}"
            );
            return;
        }
        server.send(503, "application/json", "{\"cameraOk\":false,\"reason\":\"capture_failed\"}");
        return;
    }
    camera_ok = true;
    last_snapshot_ok = true;
    consecutive_snapshot_failures = 0;
    frames_served++;
    server.sendHeader("Cache-Control", "no-store");
    server.send_P(200, "image/jpeg", reinterpret_cast<const char*>(frame->buf), frame->len);
    esp_camera_fb_return(frame);
}
}  // namespace

void setup() {
    Serial.begin(115200);
    boot_ms = millis();
    connectWiFi();
    setupCamera();

    static const char* kCollectedHeaders[] = {INSPECTION_HTTP_AUTH_HEADER};
    server.collectHeaders(kCollectedHeaders, 1);
    server.on("/api/v1/camera/health", HTTP_GET, handleHealth);
    server.on("/api/v1/camera/snapshot", HTTP_GET, handleSnapshot);
    server.begin();
}

void loop() {
    server.handleClient();
    serviceWiFi();
    delay(2);
}
