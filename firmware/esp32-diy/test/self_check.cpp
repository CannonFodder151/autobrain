// Host-side self-check for the pure, hardware-independent firmware logic.
// Builds with a plain C++ compiler (no Arduino); proves PID math and the
// epoch/RTC conversions are correct before anything touches real hardware.
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../src/obd_pids.h"
using namespace autobrain;

// Mirror of the DS3231 epoch conversions (kept here so the pure math is
// testable without Wire.h). If these drift from rtc_ds3231.h the build still
// passes, but the algorithm is the same Howard-Hinnant civil calendar.
static uint32_t daysFromCivil(int y, int m, int d) {
    y -= m <= 2;
    int era = (y >= 0 ? y : y - 399) / 400;
    unsigned yoe = (unsigned)(y - era * 400);
    unsigned doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    unsigned doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return (uint32_t)(era * 146097 + (int)doe - 719468);
}
static void civilFromDays(uint32_t z, int& y, int& m, int& d) {
    z += 719468;
    int era = (z >= 0 ? z : z - 146096) / 146097;
    unsigned doe = (unsigned)(z - era * 146097);
    unsigned yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    int yy = (int)yoe + era * 400;
    unsigned doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    unsigned mp = (5 * doy + 2) / 153;
    d = doy - (153 * mp + 2) / 5 + 1;
    m = mp + (mp < 10 ? 3 : -9);
    y = yy + (m <= 2);
}
static uint32_t toEpoch(int yr, int mon, int day, int hr, int min, int sec) {
    return daysFromCivil(yr, mon, day) * 86400u + hr * 3600u + min * 60u + sec;
}

int main() {
    // PID math
    assert(pid_rpm(0x0C, 0xE8) == 826);   // (0x0CE8=3304)/4
    assert(pid_speed(0x4B) == 75);
    assert(pid_coolant(0x54) == 44);
    assert(pid_throttle(0x80) == 50);
    assert(pid_throttle(0xFF) == 100);

    // request frame
    uint8_t req[8];
    build_pid_request(req, 0x0C);
    assert(req[0] == 2 && req[1] == 1 && req[2] == 0x0C && req[7] == 0);

    // response validation
    uint8_t resp[8] = {0x41, 0x0C, 0x0C, 0xE8, 0, 0, 0, 0};
    assert(is_valid_pid_response(resp, 0x0C));
    assert(!is_valid_pid_response(resp, 0x0D));
    assert(!is_valid_pid_response(nullptr, 0x0C));

    // ignition heuristic
    assert(!bus_active(0, false));
    assert(bus_active(1, false));          // < PROBE_REQUIRED_FRAMES
    assert(!bus_active(1, false, 2));      // below threshold
    assert(bus_active(2, false, 2));       // at threshold
    assert(bus_active(0, true));           // any valid PID wins

    // trip row format
    char row[48];
    format_trip_row(row, sizeof row, 1713000000, 826, 75, 44, 50);
    assert(strcmp(row, "1713000000,826,75,44,50\n") == 0);

    // epoch conversions (known values)
    assert(toEpoch(2026, 1, 1, 0, 0, 0) == 1767225600u);
    assert(toEpoch(1970, 1, 1, 0, 0, 0) == 0u);
    assert(toEpoch(2000, 2, 29, 12, 0, 0) == 951825600u);  // leap day

    printf("all self-checks passed\n");
    return 0;
}
