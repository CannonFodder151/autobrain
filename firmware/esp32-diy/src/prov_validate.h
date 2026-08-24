#pragma once

#include <stddef.h>
#include <string.h>

// Pure provisioning-input checks (AUT-918, Security Fw1/Fw4). No Arduino deps
// so the host-side self-check can assert them.
namespace autobrain {

// Fw4: device_id must be a canonical 36-char UUID (8-4-4-4-12, hex + hyphens).
inline bool uuid_shape_ok(const char* id) {
    if (!id) return false;
    if (strlen(id) != 36) return false;
    for (size_t i = 0; i < 36; i++) {
        char c = id[i];
        if (i == 8 || i == 13 || i == 18 || i == 23) {
            if (c != '-') return false;
            continue;
        }
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
              (c >= 'A' && c <= 'F'))) {
            return false;
        }
    }
    return true;
}

// Fw4: api_url must be https:// and have a host after the scheme. The upload
// path refuses anything else (a plaintext api_url would leak the device key).
inline bool https_url_ok(const char* url) {
    if (!url) return false;
    return strncmp(url, "https://", 8) == 0 && url[8] != '\0';
}

// Fw1: the BLE provisioning write is first-write-only. Once WiFi upload is
// enabled, later writes are rejected so an on-range attacker can neither
// overwrite the creds nor re-point api_url. Re-arm requires a factory reset.
inline bool provision_write_allowed(bool already_enabled) {
    return !already_enabled;
}

// F2 (AUT-969): the provisioning write must echo the one-shot token the app
// read from BLE_CHAR_PROV_TOKEN_UUID. A non-empty exact match is required, so
// a peer that connects first can't write an attacker-chosen config without
// first reading the current token — and the token is consumed on the first
// valid write, so a captured value can't be replayed.
inline bool provision_token_ok(const char* presented, const char* expected) {
    if (!presented || !expected) return false;
    if (presented[0] == '\0' || expected[0] == '\0') return false;
    return strcmp(presented, expected) == 0;
}

// F2: provisioning writes are accepted only inside the PROVISION_WINDOW_MS
// that opens when the provisioning window starts. After it, even a connected
// app cannot push a config.
inline bool provision_window_open(uint32_t elapsed_ms, uint32_t window_ms) {
    return elapsed_ms <= window_ms;
}

// AUT-1573: the app pulls trip CSVs over BLE by writing "name@offset" to the
// read characteristic. `name` is attacker-controlled, so pin it to a plain
// completed-trip filename: "<digits>_<digits>.csv" (the RTC stamp layout
// TripStore writes). Anything else — separators, "..", non-CSV — is rejected,
// which also makes path traversal structurally impossible.
inline bool trip_read_target_ok(const char* name) {
    if (!name) return false;
    size_t len = strlen(name);
    const size_t kStamp = 15;   // YYYYMMDD_HHMMSS
    if (len != kStamp + 4) return false;
    for (size_t i = 0; i < len; i++) {
        char c = name[i];
        bool digit = c >= '0' && c <= '9';
        bool okChar = digit || (i == 8 && c == '_') ||
                      (i >= kStamp && c == ".csv"[i - kStamp]);
        if (!okChar) return false;
    }
    return true;
}

}  // namespace autobrain
