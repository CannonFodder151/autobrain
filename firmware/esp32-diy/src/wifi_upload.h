#pragma once

#include <Arduino.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>

#include "ca_cert.h"
#include "config.h"
#include "prov_validate.h"
#include "trip_queue.h"
#include "upload_payload.h"
#include "wifi_cfg.h"

// ESP32 STA WiFi trip upload (AUT-918). Runs opportunistically after a trip
// ends (while 12V is still on) and again at the next boot. Every failure
// leaves the queue on disk — offline-first, trips are never lost. The HTTP
// surface is POST /devices/{device_id}/trips with X-Device-API-Key, which the
// backend dedupes on (device_id, device_trip_id), so a retry never double-logs.
namespace autobrain {

inline const char* QUEUE_PATH = "/wifi/queue.tsv";

// One queued trip line -> one trip object in the batch JSON.
inline size_t trip_object_json(const char* trip_id, uint32_t started_at,
                               uint32_t ended_at, const char* gps_json,
                               char* out, size_t n) {
    char start_iso[24], end_iso[24];
    epoch_to_iso(started_at, start_iso, sizeof start_iso);
    epoch_to_iso(ended_at, end_iso, sizeof end_iso);
    return snprintf(out, n,
                    "{\"device_trip_id\":\"%s\",\"started_at\":\"%s\","
                    "\"ended_at\":\"%s\",\"gps_samples\":%s}",
                    trip_id, start_iso, end_iso, gps_json);
}

// Parse one queued line "trip_id\tpath\tstart\tend\n".
inline bool parse_queue_line(char* line, QueuedTrip& t) {
    char* id = strtok(line, "\t");
    char* path = strtok(nullptr, "\t");
    char* start = strtok(nullptr, "\t");
    char* end = strtok(nullptr, "\t");
    if (!id || !path || !start || !end) return false;
    snprintf(t.trip_id, sizeof t.trip_id, "%s", id);
    snprintf(t.path, sizeof t.path, "%s", path);
    t.started_at = (uint32_t)strtoul(start, nullptr, 10);
    t.ended_at = (uint32_t)strtoul(end, nullptr, 10);
    return true;
}

inline String wifi_load_queue() {
    File f = LittleFS.open(QUEUE_PATH, "r");
    if (!f) return String();
    String s = f.readString();
    f.close();
    return s;
}

inline void wifi_store_queue(const char* text) {
    File f = LittleFS.open(QUEUE_PATH, FILE_WRITE);
    if (f) { f.print(text); f.close(); }
}

// Enqueue one completed trip CSV for upload (idempotent on trip_id).
inline void wifi_enqueue_trip(const char* trip_id, const char* path,
                              uint32_t started_at, uint32_t ended_at) {
    String q = wifi_load_queue();
    QueuedTrip t;
    snprintf(t.trip_id, sizeof t.trip_id, "%s", trip_id);
    snprintf(t.path, sizeof t.path, "%s", path);
    t.started_at = started_at;
    t.ended_at = ended_at;
    char buf[4096];
    snprintf(buf, sizeof buf, "%s", q.c_str());
    trip_queue_add(buf, sizeof buf, t);
    wifi_store_queue(buf);
    Serial.printf("WIFI enqueued %s (%u queued)\n", trip_id, trip_queue_count(buf));
}

// Enqueue the just-completed trip. `stamp` is the RTC filename stamp
// ("YYYYMMDD_HHMMSS"): it yields both the deterministic device_trip_id
// ("trip_<stamp>") and the CSV path. Start/end epochs come from the rows.
inline void wifi_upload_trip_from_stamp(const char* stamp) {
    char trip_id[40], path[64];
    snprintf(trip_id, sizeof trip_id, "trip_%s", stamp);
    snprintf(path, sizeof path, "/trips/%s.csv", stamp);
    File f = LittleFS.open(path, "r");
    if (!f) { Serial.printf("WIFI trip file missing: %s\n", path); return; }
    String csv = f.readString();
    f.close();
    uint32_t s = 0, e = 0;
    csv_first_last_epoch(csv.c_str(), &s, &e);
    wifi_enqueue_trip(trip_id, path, s, e);
}

class WifiUploader {
public:
    // Connect to the configured STA network within a bounded window.
    void connect(const WifiCfg& cfg, uint32_t timeout_ms = 15000) {
        WiFi.mode(WIFI_STA);
        WiFi.begin(cfg.ssid, cfg.pass);
        uint32_t start = millis();
        Serial.printf("WIFI connecting to %s...\n", cfg.ssid);
        while (WiFi.status() != WL_CONNECTED && millis() - start < timeout_ms) {
            delay(250);
        }
        if (WiFi.status() == WL_CONNECTED) {
            Serial.printf("WIFI connected (%s)\n", WiFi.localIP().toString().c_str());
        } else {
            Serial.println("WIFI connect failed");
        }
    }

    void disconnect() {
        WiFi.disconnect(true);
        WiFi.mode(WIFI_OFF);
    }

    // Upload all queued trips. Returns number the server acked (2xx). On any
    // failure the queue stays on disk for the next window/boot.
    int uploadAll(const WifiCfg& cfg) {
        if (WiFi.status() != WL_CONNECTED) return 0;
        String q = wifi_load_queue();
        if (q.length() == 0) return 0;

        String body = "{\"trips\":[";
        bool first = true;
        size_t n_lines = trip_queue_count(q.c_str());

        // Build the payload; lim to 64 trips per request (backend batch cap).
        char linebuf[160];
        char trip_ids[64][40];
        char trip_paths[64][64];
        int trip_n = 0;
        String tmp = q;
        char* save = nullptr;
        for (char* line = strtok((char*)tmp.c_str(), "\n"); line && trip_n < 64;
             line = strtok(nullptr, "\n")) {
            snprintf(linebuf, sizeof linebuf, "%s", line);
            QueuedTrip t;
            if (!parse_queue_line(linebuf, t)) continue;
            File f = LittleFS.open(t.path, "r");
            if (!f) continue;   // file gone: skip, will be dropped below
            String csv = f.readString();
            f.close();
            char gps[4096];
            csv_to_gps_json(csv.c_str(), gps, sizeof gps);
            uint32_t s = t.started_at, e = t.ended_at;
            if (!s || !e) csv_first_last_epoch(csv.c_str(), &s, &e);
            char obj[8192];
            trip_object_json(t.trip_id, s, e, gps, obj, sizeof obj);
            if (!first) body += ",";
            body += obj;
            first = false;
            snprintf(trip_ids[trip_n], 40, "%s", t.trip_id);
            snprintf(trip_paths[trip_n], 64, "%s", t.path);
            trip_n++;
        }
        body += "]}";
        if (trip_n == 0) return 0;

        char url[192];
        snprintf(url, sizeof url,
                 "%s/devices/%s/trips", cfg.api_url, cfg.device_id);
        // Fw4 defense-in-depth: never ship the key over a non-https endpoint.
        if (!autobrain::https_url_ok(cfg.api_url)) {
            Serial.println("WIFI refusing non-https api_url");
            return 0;
        }
        // Fw3: TLS with cert + hostname verification (no cleartext fallback).
        WiFiClientSecure tls;
        tls.setCACert(ROOT_CA_GTS_R4);  // embedded GTS Root R4; verifies chain
        tls.setTimeout(15000);
        HTTPClient http;
        http.setTimeout(15000);
        http.begin(tls, url);           // http.begin(Client&, url) keeps TLS
        http.addHeader("Content-Type", "application/json");
        http.addHeader("X-Device-API-Key", cfg.api_key);
        Serial.printf("WIFI POST %s (%d trips, %u bytes)\n",
                      url, trip_n, (unsigned)body.length());
        int code = http.POST(body);
        http.end();
        if (code >= 200 && code < 300) {
            // Acked: drop the trips from the on-disk queue.
            String fresh = wifi_load_queue();
            char buf[4096];
            snprintf(buf, sizeof buf, "%s", fresh.c_str());
            for (int i = 0; i < trip_n; i++) {
                trip_queue_remove(buf, sizeof buf, trip_ids[i]);
            }
            wifi_store_queue(buf);
            Serial.printf("WIFI upload acked, %u remaining\n", trip_queue_count(buf));
            return trip_n;
        }
        Serial.printf("WIFI upload failed HTTP %d\n", code);
        return 0;
    }

    // AUT-1573: push the stored DTC snapshot to the bound vehicle. The server
    // replaces its adapter-sourced code list, so this is idempotent. Returns
    // true on a 2xx. `body` comes pre-built from dtc_body_json.
    bool uploadCodes(const WifiCfg& cfg, const char* body) {
        if (WiFi.status() != WL_CONNECTED) return false;
        if (!autobrain::https_url_ok(cfg.api_url)) return false;  // Fw4
        char url[192];
        snprintf(url, sizeof url, "%s/devices/%s/codes", cfg.api_url, cfg.device_id);
        WiFiClientSecure tls;
        tls.setCACert(ROOT_CA_GTS_R4);  // embedded GTS Root R4; verifies chain
        tls.setTimeout(15000);
        HTTPClient http;
        http.setTimeout(15000);
        http.begin(tls, url);
        http.addHeader("Content-Type", "application/json");
        http.addHeader("X-Device-API-Key", cfg.api_key);
        Serial.printf("WIFI POST %s (%u bytes)\n", url, (unsigned)strlen(body));
        int code = http.POST(body);
        http.end();
        return code >= 200 && code < 300;
    }

    // AUT-2706: persist classified vehicle type from the dongle.
    bool uploadVehicleType(const WifiCfg& cfg, const char* body) {
        if (WiFi.status() != WL_CONNECTED) return false;
        if (!autobrain::https_url_ok(cfg.api_url)) return false;
        char url[192];
        snprintf(url, sizeof url, "%s/devices/%s/vehicle-type", cfg.api_url, cfg.device_id);
        WiFiClientSecure tls;
        tls.setCACert(ROOT_CA_GTS_R4);
        tls.setTimeout(15000);
        HTTPClient http;
        http.setTimeout(15000);
        http.begin(tls, url);
        http.addHeader("Content-Type", "application/json");
        http.addHeader("X-Device-API-Key", cfg.api_key);
        int code = http.POST(body);
        http.end();
        return code >= 200 && code < 300;
    }
};

}  // namespace autobrain
