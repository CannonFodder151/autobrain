#pragma once

#include <stdint.h>
#include <stddef.h>
#include <string.h>

namespace autobrain {

// One Mode-22 PID identifier (2-byte PID).
struct EvPid {
    uint16_t pid;
};

// Four EV telemetry channels per manufacturer profile.
struct EvProfile {
    const char* wmi;        // 3-char VIN prefix, e.g. "1N6"
    const char* make;       // human label for BLE / logs
    EvPid soc_pct;
    EvPid pack_v;
    EvPid pack_i;
    EvPid pack_temp;
};

// Known EV manufacturer profiles (WMI -> Mode-22 PID set).
// WMI = first 3 chars of the 17-char VIN (World Manufacturer Identifier).
// Sources: SAE J1979 §6, OEM service docs, community reverse-engineering.
// ponytail: PID tables are incomplete for some makers; add rows as EVs ship
// or community PIDs are verified. Generic fallback covers unknowns.
static const EvProfile EV_PROFILES[] = {
    { "1G1", "GM EV",
      {0xF18D}, {0xF18E}, {0xF18F}, {0xF190} },
    { "1N6", "Nissan",
      {0x016B}, {0x0156}, {0x0157}, {0x0158} },
    { "KMH", "Hyundai/Kia",
      {0x0181}, {0x0182}, {0x0183}, {0x0184} },
    { "KND", "Hyundai/Kia",
      {0x0181}, {0x0182}, {0x0183}, {0x0184} },
    { "5YJ", "Tesla",
      {0x0122}, {0x0123}, {0x0124}, {0x0125} },
    { "7SA", "Tesla",
      {0x0122}, {0x0123}, {0x0124}, {0x0125} },
    { "LRW", "Rivian",
      {0x0181}, {0x0182}, {0x0183}, {0x0184} },
    { "MAJ", "Ford EV",
      {0x0181}, {0x0182}, {0x0183}, {0x0184} },
    { "WBY", "BMW EV",
      {0x0181}, {0x0182}, {0x0183}, {0x0184} },
    { "5N3", "Volkswagen",
      {0x0181}, {0x0182}, {0x0183}, {0x0184} },
    { "JTM", "Toyota EV",
      {0x0181}, {0x0182}, {0x0183}, {0x0184} },
    { "JTJ", "Toyota EV",
      {0x0181}, {0x0182}, {0x0183}, {0x0184} },
};

static const size_t EV_PROFILES_N = sizeof(EV_PROFILES) / sizeof(EV_PROFILES[0]);

// Generic fallback profile when no WMI matches. Uses SAE J1979 generic
// OBD-II Mode-22 PIDs that many EVs answer before a VIN is decoded.
static const EvProfile GENERIC_EV = {
    "GEN", "Generic EV",
    {0x5B}, {0x10}, {0x11}, {0x05}
};

// Which channel of the profile is being decoded (payload layout differs).
enum EvChannel : uint8_t {
    EV_CH_SOC = 0,
    EV_CH_PACK_V = 1,
    EV_CH_PACK_I = 2,
    EV_CH_PACK_TEMP = 3
};

// Return the profile for a 3-char WMI prefix, or GENERIC_EV if unknown.
inline const EvProfile* ev_profile_for_wmi(const char* wmi) {
    if (!wmi || strlen(wmi) < 3) return &GENERIC_EV;
    for (size_t i = 0; i < EV_PROFILES_N; i++) {
        if (strncmp(EV_PROFILES[i].wmi, wmi, 3) == 0)
            return &EV_PROFILES[i];
    }
    return &GENERIC_EV;
}

// Mode-22 request frame builder (11-bit CAN id 0x7DF).
inline void build_mode22_request(uint8_t frame[8], uint16_t pid) {
    memset(frame, 0, 8);
    frame[0] = 0x03;   // PCI: 3 data bytes follow
    frame[1] = 0x22;   // service 22
    frame[2] = (uint8_t)((pid >> 8) & 0xFF);
    frame[3] = (uint8_t)(pid & 0xFF);
}

// Valid Mode-22 response: 0x62 + matching PID.
inline bool is_valid_mode22_response(const uint8_t* d, uint16_t pid) {
    return d && d[0] == 0x62 &&
           d[1] == (uint8_t)((pid >> 8) & 0xFF) &&
           d[2] == (uint8_t)(pid & 0xFF);
}

// Decode one Mode-22 channel from the response payload. Channel-aware
// because SOC is a single-byte percentage while pack voltage/current are
// typically two-byte (A*256 + B) under SAE J1979 scaling rules, and pack
// current is signed (charge vs. discharge). Returns the scaled value.
inline int32_t ev_decode_value(const uint8_t* data, EvChannel ch) {
    if (!data) return 0;
    if (ch == EV_CH_SOC) {
        return (int32_t)(data[3] * 100);               // percent -> percent*100
    }
    if (ch == EV_CH_PACK_I) {
        uint16_t raw = ((uint16_t)data[3] << 8) | data[4];
        int16_t signed_raw = (int16_t)raw;
        return (int32_t)((int64_t)signed_raw * 100);   // signed deciamps
    }
    if (ch == EV_CH_PACK_V) {
        uint16_t raw = ((uint16_t)data[3] << 8) | data[4];
        return (int32_t)(raw * 100);                    // decivolts
    }
    return (int32_t)(data[3] * 100);                   // temp: degC*100
}

// WMI extraction: first 3 chars of a VIN. Returns false if vin is too short.
inline bool vin_wmi(const char* vin, char out[4]) {
    if (!vin || !out) return false;
    if (strlen(vin) < 3) return false;
    memcpy(out, vin, 3);
    out[3] = '\0';
    return true;
}

}  // namespace autobrain
