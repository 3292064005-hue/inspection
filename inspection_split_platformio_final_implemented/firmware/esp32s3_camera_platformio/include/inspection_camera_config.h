#pragma once

#include <Arduino.h>

#ifndef INSPECTION_WIFI_SSID
#define INSPECTION_WIFI_SSID ""
#endif

#ifndef INSPECTION_WIFI_PASSWORD
#define INSPECTION_WIFI_PASSWORD ""
#endif

#ifndef INSPECTION_HTTP_PORT
#define INSPECTION_HTTP_PORT 80
#endif

#ifndef INSPECTION_FW_VERSION
#define INSPECTION_FW_VERSION "esp32s3-camera-pio-v1"
#endif

#ifndef INSPECTION_DEVICE_ID
#define INSPECTION_DEVICE_ID "esp32s3-cam-01"
#endif

#ifndef INSPECTION_JPEG_QUALITY
#define INSPECTION_JPEG_QUALITY 12
#endif

#ifndef INSPECTION_FRAME_SIZE
#define INSPECTION_FRAME_SIZE FRAMESIZE_VGA
#endif

#ifndef INSPECTION_HTTP_AUTH_TOKEN
#define INSPECTION_HTTP_AUTH_TOKEN ""
#endif

#ifndef INSPECTION_HTTP_AUTH_HEADER
#define INSPECTION_HTTP_AUTH_HEADER "X-Inspection-Token"
#endif

#ifndef INSPECTION_ALLOW_ANONYMOUS_HTTP
#define INSPECTION_ALLOW_ANONYMOUS_HTTP 0
#endif

#ifndef INSPECTION_WIFI_CONNECT_TIMEOUT_MS
#define INSPECTION_WIFI_CONNECT_TIMEOUT_MS 15000UL
#endif

#ifndef INSPECTION_WIFI_RECONNECT_INTERVAL_MS
#define INSPECTION_WIFI_RECONNECT_INTERVAL_MS 5000UL
#endif

#ifndef INSPECTION_WIFI_STATUS_POLL_MS
#define INSPECTION_WIFI_STATUS_POLL_MS 1000UL
#endif

#ifndef INSPECTION_CAMERA_REINIT_FAILURE_THRESHOLD
#define INSPECTION_CAMERA_REINIT_FAILURE_THRESHOLD 3U
#endif

struct CameraPinConfig {
    int pwdn;
    int reset;
    int xclk;
    int sda;
    int scl;
    int d7;
    int d6;
    int d5;
    int d4;
    int d3;
    int d2;
    int d1;
    int d0;
    int vsync;
    int href;
    int pclk;
};

inline CameraPinConfig inspection_camera_pins() {
#if defined(INSPECTION_CAMERA_PRESET_XIAO_SENSE)
    return {-1, -1, 10, 40, 39, 48, 11, 12, 14, 16, 18, 17, 15, 38, 47, 13};
#elif defined(INSPECTION_CAMERA_PRESET_ESP32S3_EYE)
    return {-1, -1, 15, 4, 5, 16, 17, 18, 12, 10, 8, 9, 11, 6, 7, 13};
#else
    return {-1, -1, 10, 40, 39, 48, 11, 12, 14, 16, 18, 17, 15, 38, 47, 13};
#endif
}
