#pragma once

#include <Arduino.h>
#include "config.h"
#include "obd_pids.h"
#include "power.h"

// NEO-8M GPS driver (UART2). Deterministic, dependency-free NMEA ingest — no
// TinyGPS / TinyGPSPlus. Drains the serial buffer once per trip-loop tick and
// updates plain scalar state that the trip loop samples directly:
//
//   GGA -> fix quality + lat/lon (deg*1e7) + satellites used
//   RMC -> status + lat/lon + speed-over-ground (km/h) + course (deg)
//
// DS3231 stays the trip-timestamp source (per deliverable 1); NMEA time is not
// used. GPS power is gated via power.h::gps_power() so the module's ~60-70 mA
// acquisition draw only exists while capturing — see docs/auto-sleep.md.
//
// The UART/GPIO wiring contract is defined in include/config.h (GPS_TX_PIN,
// GPS_RX_PIN, GPS_BAUD, GPS_PWR_PIN, GPS_MOVE_KPH).
namespace autobrain {

class GpsNeo8M {
public:
    void begin() {
        _ser.begin(GPS_BAUD, SERIAL_8N1, GPS_RX_PIN, GPS_TX_PIN);
    }

    // Drain the UART and apply any complete sentences. Call on every trip-loop
    // tick (~1 s). Returns true if a sentence changed fix state (diagnostics).
    bool update() {
        bool changed = false;
        while (_ser.available()) {
            char c = (char)_ser.read();
            if (c == '\n') {
                _line[_n] = '\0';
                if (_n && _line[0] == '$') {
                    if (strncmp(_line, "$GPGGA", 6) == 0) changed |= on_gga(_line);
                    else if (strncmp(_line, "$GPRMC", 6) == 0) changed |= on_rmc(_line);
                }
                _n = 0;
            } else if (_n < (int)sizeof(_line) - 1) {
                _line[_n++] = c;
            }
        }
        return changed;
    }

    bool has_fix() const { return _fix; }
    int32_t lat() const { return _lat; }          // deg*1e7
    int32_t lon() const { return _lon; }          // deg*1e7
    uint8_t sats() const { return _sats; }
    uint16_t kph10() const { return _kph10; }     // speed over ground, km/h*10
    uint16_t course10() const { return _course10; }  // course over ground, deg*10

    // "Moving" = valid fix + non-trivial speed: the GPS-side trip-activity
    // signal. Keeps a phone-dead trip open even when CAN and ACC are absent,
    // and lets a trip close when the car stops (GPS speed drops to zero).
    bool moving() const { return _fix && _kph10 >= GPS_MOVE_KPH * 10; }

private:
    HardwareSerial _ser = HardwareSerial(2);
    char _line[96];
    int _n = 0;
    bool _fix = false;
    int32_t _lat = 0;
    int32_t _lon = 0;
    uint8_t _sats = 0;
    uint16_t _kph10 = 0;
    uint16_t _course10 = 0;

    bool on_gga(char* line) {
        bool fix = false;
        int32_t la = 0, lo = 0;
        uint8_t sats = 0;
        if (!parse_gga(line, &la, &lo, &fix, &sats)) {
            if (sats) _sats = sats;  // keep sat count visible pre-fix
            return false;
        }
        _sats = sats;
        if (fix) { _fix = true; _lat = la; _lon = lo; }
        return fix;
    }

    bool on_rmc(char* line) {
        bool active = false;
        int32_t la = 0, lo = 0;
        uint32_t kph10 = 0, course10 = 0;
        if (!parse_rmc(line, &active, &la, &lo, &kph10, &course10)) return false;
        if (!active) return false;
        _fix = true; _lat = la; _lon = lo;   // RMC can front-run/finish GGA
        _kph10 = (uint16_t)kph10;
        _course10 = (uint16_t)course10;
        return true;
    }
};

}  // namespace autobrain