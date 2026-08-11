// AutoBrain phone-free trip logger — ESP32 DIY board firmware (PoC).
//
// Deterministic-first design: hardware signals drive every decision.
//   1. Ignition detect   — CAN bus responses + ACC input pin
//   2. Trip capture      — OBD-II PIDs (RPM/speed) appended to LittleFS CSV
//   3. Low power         — deep sleep between probes (timer + ACC GPIO wake)
//   4. Sync              — BLE service exposes trip index (app pulls later)
//
// Wiring (see docs/bom.md):
//   TWAI TX=5 / RX=4  -> MCP2551/SN65HVD230 transceiver -> OBD-II 6/14
//   I2C SDA=21/SCL=22 -> DS3231 RTC (battery backed)
//   ACC=15            -> 12V ignition sense via divider (active HIGH)
//   VBUS/5V           -> 12V->5V DC-DC buck (always-on feed)

#include <Arduino.h>
#include "driver/twai.h"
#include "esp_sleep.h"
#include "config.h"
#include "obd_pids.h"
#include "rtc_ds3231.h"
#include "trip_store.h"
#include "ble_sync.h"

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

// ---------- Trip loop ----------
static void run_trip() {
    char stamp[24];
    rtc.stamp(stamp, sizeof stamp);
    if (!trips.beginTrip(stamp)) {
        Serial.println("ERR: cannot open trip file");
        return;
    }
    ble.publishTrips(trips.index());

    uint32_t quiet = 0;
    while (true) {
        bool any = false;
        if (can_ok) {
            uint8_t rpm[8], spd[8];
            bool have_rpm = pid_request(0x0C, rpm);
            bool have_spd = pid_request(0x0D, spd);
            bool acc = digitalRead(ACC_PIN) == HIGH;
            if (have_rpm || have_spd || acc) {
                quiet = 0;
                char row[48];
                format_trip_row(row, sizeof row, rtc.unixTime(),
                                have_rpm ? pid_rpm(rpm[2], rpm[3]) : 0,
                                have_spd ? pid_speed(spd[2]) : 0,
                                0, 0);
                trips.appendRow(row);
                any = true;
            }
        } else if (digitalRead(ACC_PIN) == HIGH) {
            // CAN absent: fall back to ACC-only heartbeat rows.
            quiet = 0;
            char row[48];
            format_trip_row(row, sizeof row, rtc.unixTime(), 0, 0, 0, 0);
            trips.appendRow(row);
            any = true;
        }

        if (!any) quiet += SAMPLE_MS;
        if (quiet >= TRIP_END_MS) break;  // sustained silence => engine off
        delay(SAMPLE_MS);
    }

    if (trips.endTrip()) {
        trips.refreshIndex();
        ble.publishTrips(trips.index());
    }
}

// ---------- Deep sleep ----------
static void sleep_until_ignition() {
    // Timer wake: re-probe even if ACC pin never rises (some cars wake CAN only).
    esp_sleep_enable_timer_wakeup((uint64_t)SLEEP_CHECK_MS * 1000ULL);
    // GPIO wake: ACC rising edge catches engine start instantly.
    gpio_wakeup_enable((gpio_num_t)ACC_PIN, GPIO_INTR_HIGH_LEVEL);
    esp_sleep_enable_gpio_wakeup();
    esp_deep_sleep_start();  // never returns; reboot re-runs setup()
}

// ---------- Setup ----------
void setup() {
    Serial.begin(115200);
    delay(200);

    pinMode(ACC_PIN, INPUT_PULLDOWN);

    if (!rtc.begin(Wire, I2C_SDA_PIN, I2C_SCL_PIN)) {
        Serial.println("WARN: DS3231 not found — timestamps will be 0");
    }
    trips.begin();
    ble.begin(APP_NAME);
    can_init();

    Serial.printf("%s v%s boot — probing ignition...\n", APP_NAME, APP_VERSION);
    if (ignition_on(IGNITION_PROBE_MS, nullptr)) {
        Serial.println("ignition ON — capturing trip");
        run_trip();
        Serial.println("trip ended — sleeping");
    } else {
        Serial.println("ignition OFF — sleeping");
    }
    sleep_until_ignition();
}

void loop() {}  // unused; setup() deep-sleeps or loops in run_trip
