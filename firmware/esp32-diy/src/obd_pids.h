#pragma once

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
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

// Row: epoch,rpm,speed,coolant,throttle,soc_pct,pack_v,pack_a,pack_temp_c,odo_km,ev_mode,lat,lon
// EV/PHEV fields default to sentinel values so old callers and short rows from
// pre-EV firmware still parse correctly (backward-compatible).
inline int format_trip_row(char* buf, size_t bufsz, uint32_t epoch,
                           uint16_t rpm, uint8_t speed, int8_t coolant, uint8_t throttle,
                           uint8_t soc_pct = 255, uint16_t pack_v = 0, int16_t pack_a = 0,
                           int8_t pack_temp_c = -128, uint32_t odo_km = 0, uint8_t ev_mode = 0,
                           int32_t lat_1e7 = 0, int32_t lon_1e7 = 0) {
    return snprintf(buf, bufsz,
                    "%lu,%u,%u,%d,%u,%u,%u,%d,%d,%u,%u,%ld,%ld\n",
                    (unsigned long)epoch, (unsigned)rpm, (unsigned)speed,
                    (int)coolant, (unsigned)throttle,
                    (unsigned)soc_pct, (unsigned)pack_v, (int)pack_a, (int)pack_temp_c,
                    (unsigned)odo_km, (unsigned)ev_mode,
                    (long)lat_1e7, (long)lon_1e7);
}

// CSV header written once at trip start.
inline const char* trip_header() {
    return "epoch,rpm,speed,coolant,throttle,soc_pct,pack_v,pack_a,pack_temp_c,odo_km,ev_mode,lat,lon\n";
}

// NMEA-0183 GGA fix quality: 0 = invalid, >0 = valid fix. Pure, host-testable.
inline bool nmea_fix_ok(const char* fix_field) {
    return fix_field && *fix_field >= '1' && *fix_field <= '6';
}

// Convert NMEA ddmm.mmmmm (+N/S|E/W) to signed degrees*1e7.
// Returns true on a plausible coordinate; out is set to 0 on failure.
inline bool nmea_to_1e7(const char* raw, const char* hemi, int32_t* out) {
    if (!raw || !hemi || !out) return false;
    const char* dot = strchr(raw, '.');
    if (!dot) return false;
    const int deg_digits = (dot - raw) == 4 ? 2 : ((dot - raw) == 5 ? 3 : 0);
    if (!deg_digits) return false;
    char dbuf[4] = {0};
    char mbuf[3] = {0};
    memcpy(dbuf, raw, deg_digits);
    memcpy(mbuf, raw + deg_digits, 2);   // minutes digits before the dot
    int deg = atoi(dbuf);
    int min = atoi(mbuf);
    int64_t min_frac = 0;                // fractional minutes as scaled .mmmmm
    int n = 0;
    for (const char* p = dot + 1; *p && n < 5; ++p, ++n)
        min_frac = min_frac * 10 + (*p - '0');
    while (n++ < 5) min_frac *= 10;
    if (min > 59 || deg > 180) return false;
    if (hemi[1] || (hemi[0] != 'N' && hemi[0] != 'S' && hemi[0] != 'E' && hemi[0] != 'W'))
        return false;                       // malformed hemisphere
    int64_t v = (int64_t)deg * 10000000 + ((int64_t)min * 100000 + min_frac) * 10000000 / 6000000;
    if (*hemi == 'S' || *hemi == 'W') v = -v;
    *out = (int32_t)v;
    return true;
}

// Parse a NMEA GGA sentence into lat/lon (degrees*1e7) + fix validity + sats.
// Fields: $GPGGA,time,lat,N,lon,E,fix,sats,...
// Returns true and sets lat/lon/fix on a valid fix. `sats` (satellites used in
// the fix) is always set when the field is present, fix or not.
inline bool parse_gga(char* line, int32_t* lat, int32_t* lon, bool* fix,
                      uint8_t* sats = nullptr) {
    if (!line || !lat || !lon || !fix) return false;
    char* f[15] = {0};
    int n = 0;
    char* s = line;
    f[n++] = s;
    for (; *s && n < 15; ++s) {
        if (*s == ',') { f[n++] = s + 1; *s = '\0'; }
    }
    if (n < 7 || strcmp(f[0], "$GPGGA") != 0) return false;
    *fix = nmea_fix_ok(f[6]);
    if (sats && n >= 8) *sats = (uint8_t)atoi(f[7]);   // truncated GGA: leave sats
    int32_t la = 0, lo = 0;
    bool ok_lat = nmea_to_1e7(f[2], f[3], &la);
    bool ok_lon = nmea_to_1e7(f[4], f[5], &lo);
    if (!*fix || !ok_lat || !ok_lon) { *lat = 0; *lon = 0; return false; }
    *lat = la; *lon = lo;
    return true;
}

// Parse a non-negative decimal into tenths ("125.5" -> 1255). Used for RMC
// speed (knots) and course (deg). Rejects empty/garbage strings.
inline bool nmea_decimal10(const char* s, uint32_t* out10) {
    if (!s || !*s || !out10) return false;
    uint32_t ip = 0, frac = 0, scale = 1;
    const char* p = s;
    while (*p >= '0' && *p <= '9') { ip = ip * 10 + (uint32_t)(*p - '0'); p++; }
    if (*p == '.') {
        p++;
        while (*p >= '0' && *p <= '9') {
            frac = frac * 10 + (uint32_t)(*p - '0');
            scale *= 10;
            p++;
        }
    }
    if (p == s || *p) return false;              // no digits, or trailing junk
    while (scale < 10) { frac *= 10; scale *= 10; }   // pad to one decimal
    if (scale >= 100) frac = (frac + scale / 20) / (scale / 10);  // round to 1dp
    *out10 = ip * 10 + frac;
    return true;
}

// NMEA speed: knots (x10) -> km/h (x10). 1 knot = 1.852 km/h.
inline uint32_t nmea_knots10_to_kph10(uint32_t knots10) {
    return (knots10 * 1852u + 500u) / 1000u;
}

// Parse a NMEA RMC sentence into status + position + speed/course.
// Fields: $GPRMC,time,status,lat,N,lon,E,knots,course,date,... (status A=active)
// Sets *active from the status field; lat/lon (degrees*1e7), speed (km/h*10)
// and course (deg*10) only when active. Pure, host-testable.
inline bool parse_rmc(char* line, bool* active, int32_t* lat, int32_t* lon,
                      uint32_t* kph10, uint32_t* course10) {
    if (!line || !active || !lat || !lon || !kph10 || !course10) return false;
    char* f[13] = {0};
    int n = 0;
    char* s = line;
    f[n++] = s;
    for (; *s && n < 13; ++s) {
        if (*s == ',') { f[n++] = s + 1; *s = '\0'; }
    }
    if (n < 10 || strcmp(f[0], "$GPRMC") != 0) return false;
    *active = f[2] && f[2][0] == 'A';
    if (!*active) { *lat = 0; *lon = 0; *kph10 = 0; *course10 = 0; return true; }
    int32_t la = 0, lo = 0;
    bool ok_lat = nmea_to_1e7(f[3], f[4], &la);
    bool ok_lon = nmea_to_1e7(f[5], f[6], &lo);
    if (!ok_lat || !ok_lon) return false;
    *lat = la; *lon = lo;
    uint32_t knots10 = 0, crs = 0, k10 = 0;
    if (!nmea_decimal10(f[7], &knots10)) return false;
    if (!nmea_decimal10(f[8], &crs)) return false;   // course tenths of a degree
    k10 = nmea_knots10_to_kph10(knots10);
    if (k10 > 65535) return false;
    *kph10 = k10;
    *course10 = crs;
    return true;
}

// Heuristic ignition state from a probe window.
inline bool bus_active(uint32_t responses, bool any_valid_pid, uint32_t required = 2) {
    return responses >= required || any_valid_pid;
}

}  // namespace autobrain
