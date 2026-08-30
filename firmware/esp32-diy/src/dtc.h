#pragma once

#include <stdint.h>
#include <stdio.h>
#include <string.h>

// DTC (diagnostic trouble code) read/clear over OBD-II CAN (AUT-1573).
//
// Mode 03 reads stored codes, mode 04 clears them and turns off the MIL.
// Only single-frame responses are handled: every code the ECU reports fits
// the standard 2-byte DTC encoding, and a bus that answers RPM PIDs answers
// mode 03 the same way. Pure helpers here are host-tested in self_check.cpp;
// nothing in this header touches Arduino/TWAI.

namespace autobrain {

// ISO-TP single-frame request for one service byte (03 read / 04 clear):
// PCI=1 data byte (the service id), rest zero-padded to the 8-byte CAN frame.
inline void build_dtc_request(uint8_t out[8], uint8_t service) {
    memset(out, 0, 8);
    out[0] = 1;          // PCI: one data byte follows
    out[1] = service;    // 0x03 = show stored DTCs, 0x04 = clear + MIL off
}

// Decode one 2-byte DTC into "P0301"-style text (5 chars + NUL). Layout:
// [b1.7:6]=system (P/C/B/U), [b1.5:4]=first digit (0-3), [b1.3:0]=second,
// [b2.7:4]=third, [b2.3:0]=fourth. Returns false for an all-zero pair
// (ECU padding), which is not a code.
inline bool dtc_from_pair(uint8_t b1, uint8_t b2, char* out) {
    static const char systems[4] = {'P', 'C', 'B', 'U'};
    if (b1 == 0 && b2 == 0) return false;
    snprintf(out, 6, "%c%X%X%X%X", systems[(b1 >> 6) & 0x03],
             (unsigned)((b1 >> 4) & 0x03), (unsigned)(b1 & 0x0F),
             (unsigned)(b2 >> 4), (unsigned)(b2 & 0x0F));
    return true;
}

// Parse one mode-03 positive response frame (0x43). [data,len] is the full
// 8-byte CAN frame as received. Appends up to max_out "P0301"-style strings
// (6 bytes each incl NUL) to out, skipping padding pairs. Returns the number
// written. Malformed frames parse to whatever valid pairs they carry.
inline size_t parse_dtc_response(const uint8_t* data, size_t len,
                                 char out[][6], size_t max_out) {
    if (!data || len < 3 || data[1] != 0x43) return 0;
    size_t count = data[2];
    if (count > (len - 3) / 2) count = (len - 3) / 2;
    size_t used = 0;
    for (size_t i = 0; i < count && used < max_out; i++) {
        char code[6];
        if (dtc_from_pair(data[3 + i * 2], data[4 + i * 2], code)) {
            memcpy(out[used++], code, 6);
        }
    }
    return used;
}

}  // namespace autobrain
