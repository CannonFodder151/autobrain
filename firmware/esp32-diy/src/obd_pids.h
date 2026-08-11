#pragma once

#include <stdint.h>
#include <string.h>

// Pure, host-testable OBD-II PID math and trip-row formatting.
// No ESP-IDF / Arduino includes here so it compiles under a plain gcc self-check.
namespace autobrain {

// RPM PID 0x0C: value = (A*256+B) / 4
inline uint16_t pid_rpm(uint8_t a, uint8_t b) {
    return (uint16_t)((a << 8) | b) / 4;
}

// Speed PID 0x0D: value = A km/h
inline uint8_t pid_speed(uint8_t a) {
    return a;
}

// Coolant PID 0x05: value = A - 40 degC
inline int8_t pid_coolant(uint8_t a) {
    return (int8_t)(a - 40);
}

// Throttle PID 0x11: value = A * 100 / 255 %
inline uint8_t pid_throttle(uint8_t a) {
    return (uint8_t)((uint16_t)a * 100 / 255);
}

// Build a mode-01 single-PID CAN request frame (11-bit id 0x7DF).
inline void build_pid_request(uint8_t frame[8], uint8_t pid) {
    memset(frame, 0, 8);
    frame[0] = 0x02;  // PCI: 2 data bytes follow
    frame[1] = 0x01;  // service 01: current data
    frame[2] = pid;
}

// OBD response is valid if service byte echoes 0x41 and PID matches.
inline bool is_valid_pid_response(const uint8_t* d, uint8_t pid) {
    return d && d[0] == 0x41 && d[1] == pid;
}

// Row: epoch,rpm,speed,coolant,throttle
inline int format_trip_row(char* buf, size_t bufsz, uint32_t epoch,
                           uint16_t rpm, uint8_t speed, int8_t coolant, uint8_t throttle) {
    return snprintf(buf, bufsz, "%lu,%u,%u,%d,%u\n",
                    (unsigned long)epoch, (unsigned)rpm, (unsigned)speed,
                    (int)coolant, (unsigned)throttle);
}

// CSV header written once at trip start.
inline const char* trip_header() { return "epoch,rpm,speed,coolant,throttle\n"; }

// Heuristic ignition state from a probe window.
inline bool bus_active(uint32_t responses, bool any_valid_pid, uint32_t required = 2) {
    return responses >= required || any_valid_pid;
}

}  // namespace autobrain
