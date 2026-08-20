#pragma once

#define APP_NAME "AutoBrain-Tripper"
#define APP_VERSION "0.2.0"

// ---- WiFi trip upload (AUT-918) ----
// Backend base URL used when the app doesn't override it during provisioning
// (self-hosted users push their own api_url over BLE). Must match the
// backend's API_V1_PREFIX.
#define DEFAULT_API_URL "https://hosted.autobrainservice.app/api/v1"

// ---- CAN (TWAI) ----
#define CAN_TX_PIN 5
#define CAN_RX_PIN 4

// CAN transceiver standby control. Wire MCP2551 RS (pin 8) / SN65HVD230 RS
// (pin 1) to a GPIO and set it here to cut transceiver current (~5mA) down to
// ~10uA during deep sleep. Set to -1 if RS is not wired.
#define CAN_STBY_PIN 18

// ---- I2C (DS3231 RTC) ----
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22
#define DS3231_I2C_ADDR 0x68

// ---- ACC / ignition detect (12V -> divider -> GPIO, active HIGH) ----
#define ACC_PIN 15

// ---- GPS (NEO-8M, UART2) ----
#define GPS_TX_PIN 17               // ESP32 TX2 -> NEO-8M RX
#define GPS_RX_PIN 16               // ESP32 RX2 <- NEO-8M TX
#define GPS_BAUD 9600               // NEO-8M default NMEA output

// GPS power gate. GPIO drives a small NPN/MOSFET switch feeding the NEO-8M VIN,
// so the module's ~60-70 mA acquisition draw only exists while a trip is being
// captured. Set to -1 only if VIN is hard-wired to 3.3V (the NEO-8M then keeps
// drawing current in deep sleep — see docs/auto-sleep.md).
#define GPS_PWR_PIN 14

// Movement threshold (km/h): a GPS fix at/above this speed counts as trip
// activity, keeping a phone-dead trip open even with no CAN/ACC frames.
#define GPS_MOVE_KPH 3

// ---- Trip sampling ----
#define SAMPLE_MS 1000              // per-row sample interval while trip live
#define TRIP_END_MS 45000           // sustained silence (no CAN, no ACC) before closing trip
#define IGNITION_PROBE_MS 2000      // ignition check window at boot
#define PROBE_REQUIRED_FRAMES 2     // CAN responses needed to call bus active

// ---- Deep sleep ----
#define SLEEP_CHECK_MS (2u * 60u * 1000u)  // periodic wake to re-probe ignition
                                          // (CAN-only cars with no ACC line)

// ---- WiFi upload window (AUT-918) ----
#define WIFI_CONNECT_MS 12000               // STA connect budget per attempt
#define UPLOAD_BOOT_MS 4000                 // drain attempt budget at boot
#define UPLOAD_WINDOW_MS 25000              // upload budget right after a trip
#define MAX_UPLOAD_ATTEMPTS 3               // connect+post tries per window
#define WIFI_BACKOFF_BASE_MS 2000           // retry backoff (doubles)
#define WIFI_BACKOFF_CAP_MS 10000
#define PROVISION_WINDOW_MS 120000          // first-time BLE provisioning window
// F2 (AUT-969): one-shot provisioning token length in hex chars (16 = 64-bit).
#define PROV_TOKEN_HEX_LEN 16
