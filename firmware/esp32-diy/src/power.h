#pragma once

#include <Arduino.h>
#include "driver/gpio.h"
#include "esp_sleep.h"
#include "config.h"

// Deep-sleep plumbing for auto-sleep when the car is off. Everything here is
// deterministic hardware control — no AI, no heuristics beyond the timer/ACC
// wake pair the whole board design depends on.

namespace autobrain {

// MCP2551/SN65HVD230 standby: RS pin HIGH selects low-power receive-only mode
// (~10uA vs ~5mA in high-speed). Value is held with gpio_hold so it survives
// deep sleep (all GPIO state otherwise resets on wake).
static inline void can_standby(bool standby) {
#if CAN_STBY_PIN >= 0
    pinMode(CAN_STBY_PIN, OUTPUT);
    digitalWrite(CAN_STBY_PIN, standby ? HIGH : LOW);
    if (standby) {
        gpio_hold_en((gpio_num_t)CAN_STBY_PIN);
    } else {
        gpio_hold_dis((gpio_num_t)CAN_STBY_PIN);
    }
#else
    (void)standby;
#endif
}

// NEO-8M GPS power gate. GPS_PWR_PIN drives a small NPN/MOSFET switch feeding
// the module's VIN; HIGH = powered, LOW = off. The off-state is gpio-held so it
// survives deep sleep (GPS only runs while a trip is being captured). If the
// module's VIN is hard-wired to 3.3V (GPS_PWR_PIN = -1), the NEO-8M keeps
// drawing its idle/NMEA current in sleep — see docs/auto-sleep.md for the
// budget hit and why the switch is recommended.
static inline void gps_power(bool on) {
#if GPS_PWR_PIN >= 0
    pinMode(GPS_PWR_PIN, OUTPUT);
    digitalWrite(GPS_PWR_PIN, on ? HIGH : LOW);
    if (on) {
        gpio_hold_dis((gpio_num_t)GPS_PWR_PIN);
    } else {
        gpio_hold_en((gpio_num_t)GPS_PWR_PIN);
    }
#else
    (void)on;
#endif
}

// Human-readable wake cause for bench observability of the sleep state machine.
static inline const char* wake_cause_str() {
    switch (esp_sleep_get_wakeup_cause()) {
        case ESP_SLEEP_WAKEUP_EXT0: return "EXT0 (ACC pin)";
        case ESP_SLEEP_WAKEUP_EXT1: return "EXT1";
        case ESP_SLEEP_WAKEUP_TIMER: return "timer (re-probe)";
        case ESP_SLEEP_WAKEUP_TOUCHPAD: return "touchpad";
        case ESP_SLEEP_WAKEUP_ULP: return "ULP";
        case ESP_SLEEP_WAKEUP_GPIO: return "gpio (ACC high)";
        default: return "boot/power-on";
    }
}

// Enter deep sleep until the car comes back on:
//   - ACC pin high (GPIO level wake) catches engine start instantly;
//   - timer wake re-probes the CAN bus for cars that only wake CAN on ignition
//     and never pull the ACC line.
// Quiet quiescent current: ESP32 deep-sleep (~10uA) + buck no-load.
__attribute__((noreturn)) static inline void sleep_until_ignition() {
    esp_deep_sleep_disable_rom_logging();  // suppress boot ROM chatter, saves power too
    can_standby(true);                     // transceiver -> receive-only standby
    gps_power(false);                      // NEO-8M off in sleep (~60-70 mA draw)
    esp_sleep_enable_timer_wakeup((uint64_t)SLEEP_CHECK_MS * 1000ULL);
    gpio_wakeup_enable((gpio_num_t)ACC_PIN, GPIO_INTR_HIGH_LEVEL);
    esp_sleep_enable_gpio_wakeup();
    esp_deep_sleep_start();  // never returns; wake re-runs setup()
}

}  // namespace autobrain
