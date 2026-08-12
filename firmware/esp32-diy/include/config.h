#pragma once

#define APP_NAME "AutoBrain-Tripper"
#define APP_VERSION "0.1.0"

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

// ---- Trip sampling ----
#define SAMPLE_MS 1000              // per-row sample interval while trip live
#define TRIP_END_MS 45000           // sustained silence (no CAN, no ACC) before closing trip
#define IGNITION_PROBE_MS 2000      // ignition check window at boot
#define PROBE_REQUIRED_FRAMES 2     // CAN responses needed to call bus active

// ---- Deep sleep ----
#define SLEEP_CHECK_MS (2u * 60u * 1000u)  // periodic wake to re-probe ignition
                                          // (CAN-only cars with no ACC line)
