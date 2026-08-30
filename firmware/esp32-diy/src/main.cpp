// AutoBrain phone-free trip logger — ESP32 DIY board firmware (PoC).
//
// Deterministic-first design: hardware signals drive every decision.
//   1. Ignition detect   — CAN bus responses + ACC input pin
//   2. Trip capture      — OBD-II PIDs (RPM/speed) appended to LittleFS CSV
//   3. GPS position      — NEO-8M UART feed, lat/lon appended per row (route-on-map)
//   4. Low power         — deep sleep between probes (timer + ACC GPIO wake)
//   5. Sync              — BLE service exposes trip index (app pulls later)
//
// Wiring (see ../docs/obd2-dongle/01-bom.md):
//   TWAI TX=5 / RX=4  -> MCP2551/SN65HVD230 transceiver -> OBD-II 6/14
//   I2C SDA=21/SCL=22 -> DS3231 RTC (battery backed)
//   ACC=15            -> 12V ignition sense via divider (active HIGH)
//   GPS TX=17/RX=16   -> NEO-8M UART (9600 baud NMEA) + GPS_PWR_PIN gate
//                        (powered only while a trip is live)
//   VBUS/5V           -> 12V->5V DC-DC buck (always-on feed)

#include <Arduino.h>
#include "driver/twai.h"
#include "config.h"
#include "dtc.h"
#include "obd_pids.h"
#include "rtc_ds3231.h"
#include "trip_store.h"
#include "ble_sync.h"
#include "sleep_heuristics.h"
#include "power.h"
#include "gps_neo8m.h"
#include "wifi_cfg.h"
#include "wifi_upload.h"

using namespace autobrain;

static RtcDs3231 rtc;
static TripStore trips;
static BleSync ble;

// ---------- CAN ----------
static bool can_ok = false;

static void can_init() {
    twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT(
        (gpio_num_t)CAN_TX_PIN, (gpio_num_t)CAN_RX_PIN, TWAI_MODE_NORMAL);
    g.intr_flags = ESP_INTR_FLAG_LEVEL1;
    twai_timing_config_t t = TWAI_TIMING_CONFIG_500KBITS();  // OBD-II standard CAN
    twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL();
    if (twai_driver_install(&g, &t, &f) == ESP_OK &&
        twai_start() == ESP_OK) {
        can_ok = true;
    }
}

// Request one mode-01 PID; true on a valid 0x7E8 response within window.
static bool pid_request(uint8_t pid, uint8_t out[8], uint32_t timeout_ms = 80) {
    uint8_t req[8];
    build_pid_request(req, pid);
    twai_message_t msg = {};
    msg.identifier = 0x7DF;
    msg.data_length_code = 8;
    memcpy(msg.data, req, 8);
    if (twai_transmit(&msg, pdMS_TO_TICKS(20)) != ESP_OK) return false;

    uint32_t end = millis() + timeout_ms;
    while ((int32_t)(end - millis()) > 0) {
        twai_message_t rx;
        if (twai_receive(&rx, pdMS_TO_TICKS(10)) != ESP_OK) continue;
        if (rx.data_length_code >= 3 && is_valid_pid_response(rx.data, pid)) {
            memcpy(out, rx.data, 8);
            return true;
        }
    }
    return false;
}

// Probe window: count valid responses + ACC. Bus "alive" = ignition on.
static bool ignition_on(uint32_t probe_ms, uint32_t* responses_out) {
    bool acc = digitalRead(ACC_PIN) == HIGH;
    uint32_t responses = 0;
    if (can_ok) {
        uint8_t resp[8];
        uint32_t end = millis() + probe_ms;
        while ((int32_t)(end - millis()) > 0) {
            if (pid_request(0x0C, resp)) responses++;
            delay(30);
        }
    }
    if (responses_out) *responses_out = responses;
    return acc || bus_active(responses, false, PROBE_REQUIRED_FRAMES);
}

// ---------- DTC read / clear (AUT-1573) ----------
// Snapshot of the ECU's stored codes, refreshed while driving and persisted
// to /dtc/current.txt so the app can pull it over BLE or WiFi at any time.
static char dtc_codes[16][6];
static size_t dtc_n = 0;
static bool dtc_valid = false;   // true once the ECU answered a mode-03

static void dtc_store_save() {
    File f = LittleFS.open("/dtc/current.txt", FILE_WRITE);
    if (!f) return;
    for (size_t i = 0; i < dtc_n; i++) {
        f.print(dtc_codes[i]);
        f.print("\n");
    }
    f.close();
}

static String dtc_text() {
    String s;
    for (size_t i = 0; i < dtc_n; i++) {
        s += dtc_codes[i];
        s += "\n";
    }
    return s;
}

// One mode-03 exchange: refreshes the snapshot. True when the ECU answered.
static bool dtc_read_now() {
    if (!can_ok) return false;
    uint8_t req[8], resp[8];
    build_dtc_request(req, 0x03);
    twai_message_t msg = {};
    msg.identifier = 0x7DF;
    msg.data_length_code = 8;
    memcpy(msg.data, req, 8);
    if (twai_transmit(&msg, pdMS_TO_TICKS(20)) != ESP_OK) return false;
    uint32_t end = millis() + 120;
    while ((int32_t)(end - millis()) > 0) {
        twai_message_t rx;
        if (twai_receive(&rx, pdMS_TO_TICKS(10)) != ESP_OK) continue;
        if (rx.data_length_code >= 3 && rx.data[1] == 0x43) {
            dtc_n = parse_dtc_response(rx.data, rx.data_length_code, dtc_codes, 16);
            dtc_valid = true;
            return true;
        }
    }
    return false;
}

// BLE "clear" hook: mode 04 erases stored codes + turns off the MIL.
static const char* dtc_clear_now() {
    if (!can_ok) return "err:no can bus";
    uint8_t req[8];
    build_dtc_request(req, 0x04);
    twai_message_t msg = {};
    msg.identifier = 0x7DF;
    msg.data_length_code = 8;
    memcpy(msg.data, req, 8);
    if (twai_transmit(&msg, pdMS_TO_TICKS(20)) != ESP_OK) return "err:bus busy";
    uint32_t end = millis() + 120;
    while ((int32_t)(end - millis()) > 0) {
        twai_message_t rx;
        if (twai_receive(&rx, pdMS_TO_TICKS(10)) != ESP_OK) continue;
        if (rx.data_length_code >= 2 && rx.data[1] == 0x44) {
            dtc_n = 0;
            dtc_valid = true;
            dtc_store_save();
            ble.publishDtc("");
            return "ok";
        }
    }
    return "err:ecu did not confirm";
}

// ---------- GPS (NEO-8M, UART2) ----------
static GpsNeo8M gps;

// Power the module + start the UART. Called only at trip start: GPS is off
// during sleep and boot-while-parked, so its ~60-70 mA acquisition draw never
// taxes the battery (see docs/auto-sleep.md).
static void gps_start() {
    gps.begin();
    gps_power(true);
    Serial.println("GPS powered — wait for fix (antenna near window)");
}

// ---------- Trip loop ----------
static void run_trip() {
    char stamp[24];
    rtc.stamp(stamp, sizeof stamp);
    if (!trips.beginTrip(stamp)) {
        Serial.println("ERR: cannot open trip file");
        return;
    }
    ble.begin(APP_NAME);  // BLE radio only while capturing — off during sleep/probes
    ble.publishTrips(trips.index());
    if (dtc_valid) ble.publishDtc(dtc_text());
    gps_start();

    uint32_t quiet = 0;
    uint32_t rows = 0;
    while (true) {
        gps.update();                       // drain NMEA, refresh fix state
        int32_t lat = gps.lat(), lon = gps.lon();
        bool gps_moving = gps.moving();     // fix + speed: phone-dead movement
        bool any = false;
        if (can_ok) {
            uint8_t rpm[8], spd[8];
            bool have_rpm = pid_request(0x0C, rpm);
            bool have_spd = pid_request(0x0D, spd);
            bool acc = digitalRead(ACC_PIN) == HIGH;
            if (have_rpm || have_spd || acc || gps_moving) {
                char row[64];
                format_trip_row(row, sizeof row, rtc.unixTime(),
                                have_rpm ? pid_rpm(rpm[2], rpm[3]) : 0,
                                have_spd ? pid_speed(spd[2]) : 0,
                                0, 0, lat, lon);
                trips.appendRow(row);
                any = true;
                // Refresh the stored-code snapshot periodically while the
                // bus is alive (AUT-1573) — codes are unreadable once the
                // engine is off, so this window is the only chance.
                if (++rows % DTC_POLL_ROWS == 0 && dtc_read_now()) {
                    dtc_store_save();
                    ble.publishDtc(dtc_text());
                }
            }
        } else if (digitalRead(ACC_PIN) == HIGH || gps_moving) {
            // CAN absent: ACC-only / GPS-movement heartbeat rows.
            char row[64];
            format_trip_row(row, sizeof row, rtc.unixTime(), 0, 0, 0, 0, lat, lon);
            trips.appendRow(row);
            any = true;
        }

        // Trip-gating invariant (sleep_heuristics.h): any activity resets the
        // quiet window, so sleep only becomes eligible between trips.
        quiet = next_quiet(quiet, any, SAMPLE_MS);
        if (should_sleep(quiet, TRIP_END_MS)) break;  // sustained silence => engine off
        delay(SAMPLE_MS);
    }

    if (trips.endTrip()) {
        trips.refreshIndex();
        ble.publishTrips(trips.index());
        // Offline-first: the completed trip is on flash and queued for the
        // WiFi upload (done once, after run_trip, in setup()). It stays queued
        // if WiFi is out of range — next boot/drive re-tries, idempotently.
        wifi_upload_trip_from_stamp(stamp);
    }
}

// Attempt to upload queued trips (also used to drain before the next drive).
// Bounded window + exponential backoff; failures keep the queue on disk.
static void wifi_upload_opportunity(uint32_t window_ms) {
    Preferences prefs;
    WifiCfg cfg;
    wifi_cfg_load(cfg, prefs);
    if (!cfg.enabled) return;
    ble.wifi_window(true);  // free the radio for STA (BLE server stays up)
    WifiUploader up;
    uint32_t w0 = millis();
    int attempt = 0;
    while (millis() - w0 < window_ms && attempt < MAX_UPLOAD_ATTEMPTS) {
        up.connect(cfg, WIFI_CONNECT_MS);
        if (up.uploadAll(cfg) > 0) break;       // acked everything or partial
        String q = wifi_load_queue();
        if (q.length() == 0) break;             // nothing left to send
        delay(backoff_delay_ms(attempt++, WIFI_BACKOFF_BASE_MS, WIFI_BACKOFF_CAP_MS));
        up.disconnect();
    }
    // AUT-1573: push the latest DTC snapshot once trips are drained. Only
    // when the ECU actually answered this session — never wipe app-side codes
    // because a parked board had no bus to ask.
    if (dtc_valid && WiFi.status() == WL_CONNECTED) {
        File f = LittleFS.open("/dtc/current.txt", "r");
        String lines = f ? f.readString() : String();
        if (f) f.close();
        char body[512];
        dtc_body_json(lines.c_str(), body, sizeof body);
        if (!up.uploadCodes(cfg, body)) Serial.println("WIFI codes push failed");
    }
    if (WiFi.status() == WL_CONNECTED) up.disconnect();
    ble.wifi_window(false);  // advertising resumes for the app
}

// ---------- Setup ----------
void setup() {
    Serial.begin(115200);
    delay(200);

    Serial.printf("%s v%s boot — wake cause: %s\n", APP_NAME, APP_VERSION,
                  autobrain::wake_cause_str());

    pinMode(ACC_PIN, INPUT_PULLDOWN);
    can_standby(false);  // transceiver back to high-speed mode before probing

    if (!rtc.begin(Wire, I2C_SDA_PIN, I2C_SCL_PIN)) {
        Serial.println("WARN: DS3231 not found — timestamps will be 0");
    }
    trips.begin();
    LittleFS.mkdir("/dtc");
    // Load the last snapshot so the app can read/clear codes even parked.
    if (LittleFS.exists("/dtc/current.txt")) {
        File f = LittleFS.open("/dtc/current.txt", "r");
        while (f && f.available() && dtc_n < 16) {
            String line = f.readStringUntil('\n');
            line.trim();
            if (line.length() == 5) {
                snprintf(dtc_codes[dtc_n], 6, "%s", line.c_str());
                dtc_n++;
                dtc_valid = true;
            }
        }
        if (f) f.close();
    }
    g_dtc_clear_hook = dtc_clear_now;
    can_init();
    // GPS is intentionally not started here: it is powered up (gps_start) only
    // once a trip begins, so the module draws nothing while parked or probing.

    Preferences prefs;
    WifiCfg cfg;
    wifi_cfg_load(cfg, prefs);
    if (cfg.enabled) {
        // WiFi configured: drain any queued trips before probing (failures
        // from a previous drive queue for THIS boot).
        if (wifi_load_queue().length() > 0) {
            Serial.println("wifi upload: draining queue at boot");
            wifi_upload_opportunity(UPLOAD_BOOT_MS);
        }
    } else if (digitalRead(ACC_PIN) == LOW) {
        // First-time setup: car parked, no WiFi config yet — expose a BLE
        // provisioning window so the app can push SSID/pass/API key/device id.
        // Cancelled early if config arrives (checked each loop).
        Serial.println("wifi not configured — BLE provisioning window open");
        ble.begin(APP_NAME);
        ble.publishDtc(dtc_text());
        uint32_t w0 = millis();
        while (millis() - w0 < PROVISION_WINDOW_MS) {
            Preferences chk;
            WifiCfg chkc;
            wifi_cfg_load(chkc, chk);
            if (chkc.enabled) break;
            delay(200);
        }
    }

    Serial.printf("%s v%s boot — probing ignition...\n", APP_NAME, APP_VERSION);
    if (ignition_on(IGNITION_PROBE_MS, nullptr)) {
        Serial.println("ignition ON — capturing trip");
        run_trip();
        Serial.println("trip ended — WiFi upload window");
        wifi_upload_opportunity(UPLOAD_WINDOW_MS);
        Serial.println("upload done — sleeping");
    } else {
        Serial.println("ignition OFF — sleeping");
    }
    autobrain::sleep_until_ignition();
}

void loop() {}  // unused; setup() deep-sleeps or loops in run_trip
