#pragma once

#include <stdio.h>
#include <Wire.h>

// Minimal DS3231 RTC driver. Registers read/written directly over I2C.
// Battery-backed; keeps time across 12V-off. This is the deterministic
// timestamp source so trip rows stay valid even if the phone is dead.
class RtcDs3231 {
public:
    bool begin(TwoWire& w, uint8_t sda, uint8_t scl, uint8_t addr = 0x68) {
        _wire = &w;
        _addr = addr;
        _wire->begin(sda, scl);
        _wire->beginTransmission(addr);
        return _wire->endTransmission() == 0;
    }

    // Unix time (UTC). DS3231 stores UTC; app converts to local later.
    uint32_t unixTime() {
        _wire->beginTransmission(_addr);
        _wire->write(0x00);
        _wire->endTransmission();
        uint8_t n = _wire->requestFrom((int)_addr, (int)7);
        if (n != 7) return 0;
        uint8_t sec = bcd2dec(_wire->read() & 0x7F);
        uint8_t min = bcd2dec(_wire->read() & 0x7F);
        uint8_t hr  = bcd2dec(_wire->read() & 0x3F);
        _wire->read();                       // dow, unused
        uint8_t day = bcd2dec(_wire->read());
        uint8_t mon = bcd2dec(_wire->read() & 0x1F);
        uint8_t yr  = bcd2dec(_wire->read());
        return toEpoch(yr, mon, day, hr, min, sec);
    }

    bool setUnixTime(uint32_t t) {
        uint8_t yr, mon, day, hr, min, sec;
        fromEpoch(t, yr, mon, day, hr, min, sec);
        _wire->beginTransmission(_addr);
        _wire->write(0x00);
        _wire->write(dec2bcd(sec));
        _wire->write(dec2bcd(min));
        _wire->write(dec2bcd(hr));
        _wire->write(0x01);   // dow
        _wire->write(dec2bcd(day));
        _wire->write(dec2bcd(mon));
        _wire->write(dec2bcd(yr));
        return _wire->endTransmission() == 0;
    }

    // Filename-safe UTC stamp: YYYYMMDD_HHMMSS (for trip file naming).
    void stamp(char* out, size_t bufsz) {
        uint32_t t = unixTime();
        uint8_t yr, mon, day, hr, min, sec;
        fromEpoch(t, yr, mon, day, hr, min, sec);
        snprintf(out, bufsz, "%04u%02u%02u_%02u%02u%02u",
                 (unsigned)yr + 2000, (unsigned)mon, (unsigned)day,
                 (unsigned)hr, (unsigned)min, (unsigned)sec);
    }

private:
    TwoWire* _wire = nullptr;
    uint8_t _addr = 0x68;

    static uint8_t bcd2dec(uint8_t v) { return ((v >> 4) * 10) + (v & 0x0F); }
    static uint8_t dec2bcd(uint8_t v) { return ((v / 10) << 4) | (v % 10); }

    // Howard Hinnant civil-from-days / days-from-civil algorithms.
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

    static uint32_t toEpoch(uint8_t yr, uint8_t mon, uint8_t day,
                            uint8_t hr, uint8_t min, uint8_t sec) {
        uint32_t days = daysFromCivil(2000 + yr, mon, day);
        return days * 86400u + hr * 3600u + min * 60u + sec;
    }

    static void fromEpoch(uint32_t t, uint8_t& yr, uint8_t& mon, uint8_t& day,
                          uint8_t& hr, uint8_t& min, uint8_t& sec) {
        uint32_t days = t / 86400u;
        int y, m, d;
        civilFromDays(days, y, m, d);
        yr = (uint8_t)(y - 2000);
        mon = (uint8_t)m;
        day = (uint8_t)d;
        uint32_t rem = t % 86400u;
        hr = (uint8_t)(rem / 3600u);
        min = (uint8_t)((rem % 3600u) / 60u);
        sec = (uint8_t)(rem % 60u);
    }
};
