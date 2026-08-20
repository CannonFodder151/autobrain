#pragma once

#include <stdint.h>
#include <stdio.h>
#include <string.h>

// Offline-first trip upload queue (AUT-918). PURE, host-testable: no Arduino
// or ESP-IDF includes, so the serialise/add/remove semantics are proven by the
// plain-compiler self-check before anything touches flash.
//
// A queued trip is one TSV line (tabs, no JSON lib needed on-device):
//   <trip_id>\t<path>\t<started_at>\t<ended_at>\n
// e.g.  trip-1767200000\t/trips/2026-08-01T09-00-00Z.csv\t1767200000\t1767203000
//
// The whole buffer is persisted to LittleFS as /wifi/queue.tsv. `trip_id` is
// derived from the RTC trip start epoch, so a WiFi retry re-sends the same id
// and the server's (device_id, device_trip_id) key dedupes it — idempotent.
namespace autobrain {

struct QueuedTrip {
    char trip_id[40];
    char path[64];
    uint32_t started_at;
    uint32_t ended_at;
};

inline size_t trip_queue_line(const QueuedTrip& t, char* out, size_t n) {
    return snprintf(out, n, "%s\t%s\t%u\t%u\n", t.trip_id, t.path, t.started_at, t.ended_at);
}

// Source of truth for the success decision in self-check and firmware — a trip
// id is "queued" only if its line exists verbatim by trip_id.
inline bool trip_queue_has(const char* buf, const char* trip_id) {
    if (!buf || !trip_id) return false;
    size_t id_len = strlen(trip_id);
    if (!id_len) return false;
    const char* p = buf;
    while (*p) {
        const char* nl = strchr(p, '\n');
        size_t len = nl ? (size_t)(nl - p) : strlen(p);
        if (len >= id_len && memcmp(p, trip_id, id_len) == 0 &&
            (len == id_len || p[id_len] == '\t')) {
            return true;
        }
        if (!nl) break;
        p = nl + 1;
    }
    return false;
}

// Record a completed trip for later upload. Dedupes: re-adding a trip_id that
// is already queued is a no-op. Returns the new buffer length.
inline size_t trip_queue_add(char* buf, size_t n, const QueuedTrip& t) {
    if (trip_queue_has(buf, t.trip_id)) return strlen(buf);
    char line[160];
    size_t need = trip_queue_line(t, line, sizeof line);
    size_t used = strlen(buf);
    if (used + need >= n) return used;
    memcpy(buf + used, line, need + 1);
    return used + need;
}

// Remove an uploaded trip (server acked) so retries never resend it. Returns
// the new buffer length.
inline size_t trip_queue_remove(char* buf, size_t n, const char* trip_id) {
    (void)n;
    char* out = buf;
    char* line = buf;
    size_t id_len = strlen(trip_id);
    while (line && *line) {
        char* nl = strchr(line, '\n');
        size_t len = nl ? (size_t)(nl - line) : strlen(line);
        bool match = len >= id_len && memcmp(line, trip_id, id_len) == 0 &&
                     (len == id_len || line[id_len] == '\t');
        if (!match) {
            memmove(out, line, len);
            out += len;
            *out++ = '\n';
        }
        if (!nl) break;
        line = nl + 1;
    }
    *out = '\0';
    return (size_t)(out - buf);
}

inline size_t trip_queue_count(const char* buf) {
    size_t c = 0;
    for (const char* p = buf ? buf : ""; *p; p++) if (*p == '\n') c++;
    return c;
}

// Exponential-backoff delay (ms) for upload retries within one drive.
// attempt 0 = first try (immediate); each failure doubles, capped at cap_ms.
inline uint32_t backoff_delay_ms(uint32_t attempt, uint32_t base_ms, uint32_t cap_ms) {
    if (attempt == 0) return 0;
    if (attempt > 31) return cap_ms;
    uint64_t d = (uint64_t)base_ms << (attempt - 1);
    return d > cap_ms ? cap_ms : (uint32_t)d;
}

}  // namespace autobrain