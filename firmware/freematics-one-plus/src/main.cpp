// AutoBrain phone-free trip logger — Freematics ONE+ Model B (reference path).
//
// Reference implementation for the US$135 Freematics ONE+ Model B dev board,
// using the official Freematics ONE+ SDK (COBD + SDLogger). Same deterministic
// design as the ESP32 DIY path: ignition detect via PID reads, trip rows
// appended to on-board SD, low power when the bus goes quiet, BLE sync later.
//
// NOTE: requires the Freematics ONE+ SDK / board package (freematics.com).
// Compile-verified in the repo only for the ESP32 DIY path (firmware/esp32-diy);
// this sketch is the SDK-accurate reference to run on the Model B.
//
// Wiring: Model B ships with CAN transceiver + OBD-II connector built in —
// nothing to solder. Power from the always-on OBD pin 16; unit has its own
// RTC + GNSS + flash/SD.

#include <FreematicsPlus.h>
#include <SPI.h>
#include <SD.h>
#include "OBD.h"

// --- config (kept in sync with firmware/esp32-diy/include/config.h) ---
#define SAMPLE_MS 1000
#define TRIP_END_MS 45000

class OBD : public COBD {
protected:
    void idleTasks() { delay(1); }  // yields while waiting on the bus
};
static OBD obd;
static SDLogger logger;

void setup() {
    Serial.begin(115200);
    while (!Serial) {}

    // Init Freematics platform + SD card (returns MB free; 0 = no card).
    int volsize = logger.init();
    if (volsize <= 0) {
        Serial.println("SD init failed");
    }

    // Bring up OBD on the vehicle CAN bus.
    if (!obd.init()) {
        Serial.println("OBD init failed");
    }
}

void loop() {
    static uint32_t quiet = 0;
    static uint32_t lastSample = 0;
    if (millis() - lastSample < SAMPLE_MS) return;
    lastSample = millis();

    // Ignition detect: a valid PID reply means the ECU is awake.
    int rpm = 0, speed = 0;
    bool live = obd.readPID(PID_ENGINE_RPM, rpm);
    live |= obd.readPID(PID_SPEED, speed);

    if (live) {
        quiet = 0;
        char row[32];
        // Same row schema as esp32-diy: epoch,rpm,speed (epoch=0 until app sync
        // sets the RTC; the unit's own RTC supplies it via sys.time() when wired).
        snprintf(row, sizeof row, "%lu,%d,%d\n", (unsigned long)millis() / 1000, rpm, speed);
        logger.write(row, strlen(row));
        logger.flush();
    } else {
        quiet += SAMPLE_MS;
        if (quiet >= TRIP_END_MS) {
            // Engine off: low-power mode until bus activity returns.
            obd.enterLowPowerMode();
            delay(60000);   // re-check once a minute (SD kept for logging)
            quiet = 0;
        }
    }
}
