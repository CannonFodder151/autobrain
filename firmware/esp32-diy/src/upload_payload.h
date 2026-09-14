#pragma once

#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "trip_queue.h"

// Pure payload construction for the dongle upload endpoint (AUT-918). No
// Arduino/ESP-IDF includes — the string logic is host-tested alongside the
// queue in self_check.cpp.
//
// The backend surface is POST /devices/{device_id}/trips with:
//   {"trips":[{"device_trip_id":..,"started_at":ISO,"ended_at":ISO,"gps_samples":[...]}]}
// started_at/ended_at are ISO-8601 UTC (pydantic datetime). gps_samples come
// from the board CSV rows where the last two fields are lat/lon (degrees x10^7)
// and 0,0 means "no fix" — the server re-cleans them deterministically via the
// same rules the app logbook uses. Intermediate EV fields (soc_pct, pack_v,
// pack_a, pack_temp_c, odo_km, ev_mode) are accepted by the row schema but
// currently ignored by gps extraction (lat/lon are always the last two fields).
namespace autobrain {

// epoch -> "YYYY-MM-DDTHH:MM:SSZ" (UTC, no tz lib). Howard-Hinnant civil
// arithmetic, mirror of the RTC driver so it is testable off-device.
inline void epoch_to_iso(uint32_t t, char* out, size_t n) {
    uint32_t days = t / 86400u, rem = t % 86400u;
    int z = (int)days + 719468;
    int era = (z >= 0 ? z : z - 146096) / 146097;
    unsigned doe = (unsigned)(z - era * 146097);
    unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    int yy = (int)yoe + era * 400;
    unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    unsigned mp = (5 * doy + 2) / 153;
    int d = (int)(doy - (153 * mp + 2) / 5 + 1);
    int m = (int)(mp + (mp < 10 ? 3 : -9));
    int y = yy + (m <= 2);
    uint32_t hr = rem / 3600u, mi = (rem % 3600u) / 60u, sec = rem % 60u;
    snprintf(out, n, "%04d-%02d-%02dT%02u:%02u:%02uZ", y, m, d, hr, mi, sec);
}

// Convert one trip CSV dump to a gps_samples JSON array string. Rows are
// epoch,...,lat,lon with lat/lon as degrees x10^7; 0,0 (no fix) and malformed
// rows are skipped. Tolerates both old 7-field rows and new 13-field rows
// (AUT-2703: EV/PHEV fields appended but the parser reads only fields it needs).
// Returns bytes written (excluding NUL).
inline size_t csv_to_gps_json(const char* csv, char* out, size_t n) {
    size_t used = 0;
    snprintf(out, n, "[");
    used += 1;  // "["
    const char* p = csv;
    bool first = true;
    while (*p) {
        const char* nl = strchr(p, '\n');
        size_t len = nl ? (size_t)(nl - p) : strlen(p);
        // epoch,rpm,speed,coolant,throttle,lat,lon[,soc_pct,pack_v,pack_a,pack_temp_c,odo_km,ev_mode]
        // Fixed-position reads tolerate both old (7-field) and new (13-field) rows.
        uint32_t epoch = 0;
        int32_t lat = 0, lon = 0;
        if (len > 0 &&
            sscanf(p, "%u,%*[^,],%*[^,],%*[^,],%*[^,],%d,%d", &epoch, &lat, &lon) >= 3 &&
            (lat != 0 || lon != 0)) {
            int need = snprintf(NULL, 0, "%s{\"t\":%u,\"lat\":%.7f,\"lon\":%.7f}",
                                first ? "" : ",", epoch, lat / 1e7, lon / 1e7);
            if (used + (size_t)need + 1 < n) {
                used += (size_t)snprintf(out + used, n - used,
                                         "%s{\"t\":%u,\"lat\":%.7f,\"lon\":%.7f}",
                                         first ? "" : ",", epoch, lat / 1e7, lon / 1e7);
                first = false;
            }
        }
        if (!nl) break;
        p = nl + 1;
    }
    snprintf(out + used, n - used, "]");
    return used + 1;
}

// Read the first and last row epoch from a CSV dump (start/end times).
inline void csv_first_last_epoch(const char* csv, uint32_t* first, uint32_t* last) {
    *first = *last = 0;
    const char* p = csv;
    while (*p) {
        const char* nl = strchr(p, '\n');
        size_t len = nl ? (size_t)(nl - p) : strlen(p);
        if (len > 0) {
            uint32_t e = 0;
            if (sscanf(p, "%u", &e) == 1 && e > 0) {
                if (!*first) *first = e;
                *last = e;
            }
        }
        if (!nl) break;
        p = nl + 1;
    }
}

}  // namespace autobrain
// AUT-1573: pure body builder for the DTC snapshot push — one code per line
// ("P0301\n..."), the same text the BLE DTC characteristic exposes. Anything
// not shaped like a 5-char code line is skipped. Host-tested.
inline size_t dtc_body_json(const char* lines, char* out, size_t n) {
    size_t used = 0;
    used += (size_t)snprintf(out + used, n - used, "{\"codes\":[");
    bool first = true;
    const char* p = lines;
    while (*p) {
        const char* nl = strchr(p, '\n');
        size_t len = nl ? (size_t)(nl - p) : strlen(p);
        if (len >= 5 && len <= 6) {  // "P0301" shape only
            char code[8];
            memcpy(code, p, len);
            code[len] = '\0';
            int need = snprintf(NULL, 0, "%s{\"code\":\"%s\"}", first ? "" : ",", code);
            if ((size_t)need > 0 && used + (size_t)need + 2 < n) {
                used += (size_t)snprintf(out + used, n - used,
                                         "%s{\"code\":\"%s\"}", first ? "" : ",", code);
                first = false;
            }
        }
        if (!nl) break;
        p = nl + 1;
    }
    used += (size_t)snprintf(out + used, n - used, "]}");
    return used;
}
