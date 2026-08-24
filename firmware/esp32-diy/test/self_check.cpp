// Host-side self-check for the pure, hardware-independent firmware logic.
// Builds with a plain C++ compiler (no Arduino); proves PID math and the
// epoch/RTC conversions are correct before anything touches real hardware.
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../include/config.h"
#include "../src/dtc.h"
#include "../src/obd_pids.h"
#include "../src/prov_validate.h"
#include "../src/sleep_heuristics.h"
#include "../src/upload_payload.h"
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
    assert(!bus_active(1, false));          // 1 < PROBE_REQUIRED_FRAMES (2)
    assert(!bus_active(1, false, 2));       // below threshold
    assert(bus_active(2, false, 2));       // at threshold
    assert(bus_active(0, true));           // any valid PID wins

    // trip row format
    char row[64];
    format_trip_row(row, sizeof row, 1713000000, 826, 75, 44, 50);
    assert(strcmp(row, "1713000000,826,75,44,50,0,0\n") == 0);
    format_trip_row(row, sizeof row, 1713000000, 826, 75, 44, 50, 123456789, -987654321);
    assert(strcmp(row, "1713000000,826,75,44,50,123456789,-987654321\n") == 0);

    // NMEA GPS parsing (Sydney: 33°52'S 151°12'E)
    int32_t lat = 0, lon = 0;
    assert(nmea_to_1e7("3352.12345", "S", &lat));   // 33 deg 52.12345 min
    assert(lat == -338687241);                        // -(33 + 52.12345/60) * 1e7
    assert(nmea_to_1e7("15112.65432", "E", &lon));
    assert(lon == 1512109053);                        // 151 + 12.65432/60
    assert(!nmea_to_1e7("3352.12345", "", &lat));
    assert(!nmea_to_1e7("999.9", "N", &lat));         // malformed

    // GGA parse
    char gga[] = "$GPGGA,083020.00,3352.12345,S,15112.65432,E,1,08,0.9,545.4,M,46.9,M,,*47";
    bool fix = false;
    assert(parse_gga(gga, &lat, &lon, &fix));
    assert(fix && lat == -338687241 && lon == 1512109053);
    char gga_no[] = "$GPGGA,083020.00,3352.12345,S,15112.65432,E,0,00,,,M,,M,,*48";
    assert(!parse_gga(gga_no, &lat, &lon, &fix));     // fix quality 0 = invalid
    char rmc[] = "$GPRMC,083020.00,A,3352.12345,S,15112.65432,E,0.0,,010916,,,A*6F";
    assert(!parse_gga(rmc, &lat, &lon, &fix));        // not a GGA sentence

    // GGA satellite count (visible even with a marginal fix)
    char gga2[] = "$GPGGA,083020.00,3352.12345,S,15112.65432,E,1,08,0.9,545.4,M,46.9,M,,*47";
    uint8_t sats = 0;
    fix = false;
    assert(parse_gga(gga2, &lat, &lon, &fix, &sats));
    assert(sats == 8);
    char gga_no2[] = "$GPGGA,083020.00,3352.12345,S,15112.65432,E,0,00,,,M,,M,,*48";
    assert(!parse_gga(gga_no2, &lat, &lon, &fix, &sats));
    assert(sats == 0);

    // decimal -> tenths
    uint32_t t10 = 0;
    assert(nmea_decimal10("0.00", &t10) && t10 == 0);
    assert(nmea_decimal10("0", &t10) && t10 == 0);
    assert(nmea_decimal10("125.5", &t10) && t10 == 1255);
    assert(nmea_decimal10("0.60", &t10) && t10 == 6);
    assert(nmea_decimal10("12.345", &t10) && t10 == 123);  // rounds to 1dp
    assert(!nmea_decimal10("", &t10));                     // empty
    assert(!nmea_decimal10("abc", &t10));                  // garbage
    assert(!nmea_decimal10("12.x", &t10));                 // trailing junk

    // knots -> km/h: 1 knot = 1.852 km/h (all in x10 fixed point)
    assert(nmea_knots10_to_kph10(0) == 0);
    assert(nmea_knots10_to_kph10(54) == 100);   // 5.4 kt -> 10.0 km/h
    assert(nmea_knots10_to_kph10(108) == 200);  // 10.8 kt -> 20.0 km/h

    // RMC parse: active status -> pos + speed + course
    char rmca[] = "$GPRMC,083020.00,A,3352.12345,S,15112.65432,E,5.4,125.5,010916,,,A*55";
    bool active = false;
    uint32_t kph10 = 0, course10 = 0;
    assert(parse_rmc(rmca, &active, &lat, &lon, &kph10, &course10));
    assert(active && lat == -338687241 && lon == 1512109053);
    assert(kph10 == 100 && course10 == 1255);   // 5.4 kt -> 10.0 km/h, 125.5 deg
    char rmcv[] = "$GPRMC,083020.00,V,3352.12345,S,15112.65432,E,0.0,,010916,,,N*70";
    assert(parse_rmc(rmcv, &active, &lat, &lon, &kph10, &course10));
    assert(!active && lat == 0 && lon == 0 && kph10 == 0 && course10 == 0);
    assert(!parse_rmc(gga, &active, &lat, &lon, &kph10, &course10));  // not RMC

    // epoch conversions (known values)
    assert(toEpoch(2026, 1, 1, 0, 0, 0) == 1767225600u);
    assert(toEpoch(1970, 1, 1, 0, 0, 0) == 0u);
    assert(toEpoch(2000, 2, 29, 12, 0, 0) == 951825600u);  // leap day
    // round-trip the civil<->epoch mirror (civilFromDays takes days, not seconds)
    int yr = 0, mo = 0, dy = 0;
    civilFromDays(1767225600u / 86400u, yr, mo, dy);
    assert(yr == 2026 && mo == 1 && dy == 1);
    civilFromDays(951825600u / 86400u, yr, mo, dy);
    assert(yr == 2000 && mo == 2 && dy == 29);

    // auto-sleep trip-gating invariants: any activity resets the quiet window,
    // so sleep is only eligible between trips, never mid-log.
    assert(next_quiet(0, false, 1000) == 1000);
    assert(next_quiet(44000, false, 1000) == 45000);
    assert(next_quiet(44000, true, 1000) == 0);      // activity resets window
    assert(next_quiet(0, true, 1000) == 0);          // activity while logging keeps logging
    assert(!should_sleep(44999, 45000));             // below threshold: trip stays open
    assert(should_sleep(45000, 45000));              // at threshold: eligible to sleep
    assert(should_sleep(0, 0));                      // zero threshold: immediate
    assert(!should_sleep(0, 45000));                 // fresh trip: never sleep mid-log
    // invariant: a row is written iff activity, and activity forces quiet=0,
    // so no log row is ever lost to a mid-trip sleep.
    for (uint32_t q = 0; q <= 50000; q += 1000)
        assert(next_quiet(q, true, 1000) == 0);

    // ---- trip upload queue (AUT-918) ----
    char qbuf[512] = "";
    QueuedTrip t1 = {"trip_20260801_090000", "/trips/20260801_090000.csv", 1767200400, 1767202200};
    QueuedTrip t2 = {"trip_20260801_130000", "/trips/20260801_130000.csv", 1767214800, 1767216600};
    assert(trip_queue_count(qbuf) == 0);
    assert(trip_queue_add(qbuf, sizeof qbuf, t1) > 0);
    assert(trip_queue_add(qbuf, sizeof qbuf, t2) > 0);
    assert(trip_queue_count(qbuf) == 2);
    assert(trip_queue_has(qbuf, "trip_20260801_090000"));
    assert(trip_queue_has(qbuf, "trip_20260801_130000"));
    assert(!trip_queue_has(qbuf, "trip_9999"));
    size_t before = strlen(qbuf);
    assert(trip_queue_add(qbuf, sizeof qbuf, t1) == before);  // dedupe: no-op
    assert(trip_queue_count(qbuf) == 2);
    size_t after_one = trip_queue_remove(qbuf, sizeof qbuf, "trip_20260801_090000");
    assert(trip_queue_count(qbuf) == 1);
    assert(!trip_queue_has(qbuf, "trip_20260801_090000"));
    assert(trip_queue_has(qbuf, "trip_20260801_130000"));
    assert(after_one < before);
    assert(trip_queue_remove(qbuf, sizeof qbuf, "trip_20260801_130000") == 0);
    assert(trip_queue_count(qbuf) == 0);

    // ---- upload backoff ----
    assert(backoff_delay_ms(0, 2000, 10000) == 0);    // first try immediate
    assert(backoff_delay_ms(1, 2000, 10000) == 2000); // retry 1: 2s
    assert(backoff_delay_ms(2, 2000, 10000) == 4000); // retry 2: 4s
    assert(backoff_delay_ms(3, 2000, 10000) == 8000); // retry 3: 8s
    assert(backoff_delay_ms(4, 2000, 10000) == 10000);// capped at 10s
    assert(backoff_delay_ms(32, 2000, 10000) == 10000);
    assert(backoff_delay_ms(5, 1000, 3000) == 3000);  // cap wins over doubling

    // ---- epoch -> ISO (pydantic datetime on the server) ----
    char iso[24];
    epoch_to_iso(1767225600, iso, sizeof iso);  // 2026-01-01T00:00:00Z (matches toEpoch above)
    assert(strcmp(iso, "2026-01-01T00:00:00Z") == 0);
    epoch_to_iso(0, iso, sizeof iso);
    assert(strcmp(iso, "1970-01-01T00:00:00Z") == 0);
    epoch_to_iso(1767200401, iso, sizeof iso);  // 7h earlier: 2025-12-31T17:00:01Z
    assert(strcmp(iso, "2025-12-31T17:00:01Z") == 0);

    // ---- board CSV -> gps_samples JSON (AUT-918 upload payload) ----
    char gps[512];
    const char* csv =
        "epoch,rpm,speed,coolant,throttle,lat,lon\n"
        "1767200400,826,75,44,50,0,0\n"            // no fix -> dropped
        "1767200401,830,76,44,51,-338687241,1512109053\n"
        "1767200402,840,78,45,52,-338687250,1512109060\n"
        "junk-rows-are-skipped\n"
        "1767200403,850,80,45,53,0,0\n";
    csv_to_gps_json(csv, gps, sizeof gps);
    assert(strstr(gps, "\"t\":1767200401") != NULL);
    assert(strstr(gps, "\"t\":1767200402") != NULL);
    assert(strstr(gps, "\"t\":1767200400") == NULL);  // 0,0 fix dropped
    assert(strstr(gps, "lat\":-33.8687241") != NULL);
    // Exactly two samples + array brackets.
    size_t opens = 0, closes = 0;
    for (char* c = gps; *c; c++) {
        if (*c == '{') opens++;
        if (*c == '}') closes++;
    }
    assert(opens == 2 && closes == 2);

    // ---- CSV first/last epoch -> trip start/end ----
    uint32_t fs = 0, fe = 0;
    csv_first_last_epoch(csv, &fs, &fe);
    assert(fs == 1767200400 && fe == 1767200403);

    // ---- provisioning validation (AUT-918 Security Fw1/Fw4) ----
    // Fw1: first-write-only gate — re-provisioning a configured device is
    // rejected so an on-range attacker can't overwrite creds / re-point URL.
    assert(provision_write_allowed(false));   // unconfigured: may provision
    assert(!provision_write_allowed(true));   // enabled: write rejected
    // Fw4: api_url must be https with a host after the scheme.
    assert(https_url_ok("https://hosted.autobrainservice.app/api/v1"));
    assert(!https_url_ok("http://hosted.autobrainservice.app/api/v1"));
    assert(!https_url_ok("https://"));
    assert(!https_url_ok(""));
    assert(!https_url_ok(nullptr));
    // Fw4: device_id is a canonical 36-char UUID.
    assert(uuid_shape_ok("1ef3fbc2-c204-4846-be09-64265c8924a2"));
    assert(!uuid_shape_ok("1ef3fbc2-c204-4846-be09-64265c8924a"));   // 35 chars
    assert(!uuid_shape_ok("1ef3fbc2c204-4846-be09-64265c8924a2"));    // bad hyphens
    assert(!uuid_shape_ok("1ef3fbc2-c204-4846-be09-64265c8924gg"));   // non-hex
    assert(!uuid_shape_ok(""));

    // ---- F2 (AUT-969): one-shot provisioning token ----
    // Token echo: the write must carry the exact token the app read.
    assert(provision_token_ok("0123456789abcdef", "0123456789abcdef"));
    assert(!provision_token_ok("", "0123456789abcdef"));               // absent
    assert(!provision_token_ok(nullptr, "0123456789abcdef"));          // absent
    assert(!provision_token_ok("0123456789abcdee", "0123456789abcdef"));  // mismatch
    assert(!provision_token_ok("0123456789abcdef", ""));               // consumed
    assert(!provision_token_ok("0123456789abcdef", nullptr));          // consumed
    // Window: provisioning writes accepted only inside PROVISION_WINDOW_MS.
    assert(provision_window_open(0, PROVISION_WINDOW_MS));
    assert(provision_window_open(PROVISION_WINDOW_MS, PROVISION_WINDOW_MS));
    assert(!provision_window_open(PROVISION_WINDOW_MS + 1, PROVISION_WINDOW_MS));
    assert(!provision_window_open(120001, PROVISION_WINDOW_MS));

    // ---- AUT-1573: DTC parse / clear-request frames ----
    uint8_t req3[8], req4[8];
    build_dtc_request(req3, 0x03);
    build_dtc_request(req4, 0x04);
    assert(req3[0] == 1 && req3[1] == 0x03 && req3[2] == 0);
    assert(req4[0] == 1 && req4[1] == 0x04 && req4[2] == 0);

    // dtc_from_pair: P0301 = 0000_0001 0000_0011 -> wait: P=00, d1=0, d2=3,
    // d3=0, d4=1 => b1 = (0<<6)|(0<<4)|0x03, b2 = (0x0<<4)|0x01.
    char code[6];
    assert(dtc_from_pair(0x03, 0x01, code));
    assert(strcmp(code, "P0301") == 0);
    // C1234 / B0021 / U0100 shapes.
    assert(dtc_from_pair((1 << 6) | (1 << 4) | 0x02, 0x34, code) &&
           strcmp(code, "C1234") == 0);
    assert(dtc_from_pair((2 << 6) | (0 << 4) | 0x00, 0x21, code) &&
           strcmp(code, "B0021") == 0);
    assert(dtc_from_pair((3 << 6) | (0 << 4) | 0x01, 0x00, code) &&
           strcmp(code, "U0100") == 0);
    assert(!dtc_from_pair(0x00, 0x00, code));   // padding pair is not a code

    // Mode-03 response frame: 43 02 P0301 U0100 + padding.
    {
        uint8_t frame[8] = {0x04, 0x43, 0x02, 0x03, 0x01, 0xC1, 0x00, 0x55};
        char codes[8][6];
        size_t n = parse_dtc_response(frame, sizeof frame, codes, 8);
        assert(n == 2);
        assert(strcmp(codes[0], "P0301") == 0);
        assert(strcmp(codes[1], "U0100") == 0);

        // Zero-DTC response.
        uint8_t none[8] = {0x02, 0x43, 0x00, 0x55, 0x55, 0, 0, 0};
        n = parse_dtc_response(none, sizeof none, codes, 8);
        assert(n == 0);

        // Count byte lies bigger than the payload: clamped, no overrun.
        uint8_t liar[5] = {0x04, 0x43, 0xFF, 0x03, 0x01};
        n = parse_dtc_response(liar, sizeof liar, codes, 8);
        assert(n == 1);

        // Not a mode-03 response.
        uint8_t other[8] = {0x04, 0x41, 0x0C, 0x1A, 0xF8, 0, 0, 0};
        assert(parse_dtc_response(other, sizeof other, codes, 8) == 0);
        assert(parse_dtc_response(nullptr, 8, codes, 8) == 0);
    }

    // ---- AUT-1573: BLE trip-read target validation (path-traversal proof) ----
    assert(trip_read_target_ok("20260801_090000.csv"));
    assert(!trip_read_target_ok("20260801_090000.CSV"));      // case-pinned
    assert(!trip_read_target_ok("index.txt"));                 // not a trip
    assert(!trip_read_target_ok("../wifi/queue.tsv"));         // traversal
    assert(!trip_read_target_ok("/trips/a.csv"));              // absolute path
    assert(!trip_read_target_ok("20260801_090000.csv.txt"));   // wrong ext
    assert(!trip_read_target_ok("2026801_090000.csv"));        // short stamp
    assert(!trip_read_target_ok(""));
    assert(!trip_read_target_ok(nullptr));

    // ---- AUT-1573: DTC snapshot push body ----
    {
        char body[512];
        dtc_body_json("P0301\nU0100\n", body, sizeof body);
        assert(strcmp(body,
                      "{\"codes\":[{\"code\":\"P0301\"},{\"code\":\"U0100\"}]}") == 0);
        dtc_body_json("", body, sizeof body);                  // empty snapshot
        assert(strcmp(body, "{\"codes\":[]}") == 0);
        dtc_body_json("garbage-line\nP0301\n", body, sizeof body);
        assert(strcmp(body, "{\"codes\":[{\"code\":\"P0301\"}]}") == 0);
    }

    printf("all self-checks passed\n");
    return 0;
}
