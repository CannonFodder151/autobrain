#pragma once

#include <stdint.h>

// Pure, host-testable trip-gating logic for auto-sleep. No Arduino/ESP-IDF
// includes so it compiles under a plain compiler self-check.
//
// The quiet accumulator counts how long the bus has been silent. Any activity
// (CAN response or ACC high) resets it to zero, so a trip only closes — and
// sleep only becomes eligible — after sustained silence. This is the
// "sleep only between trips, never mid-log" invariant.
namespace autobrain {

// Next accumulator value after one sample of the given activity.
inline uint32_t next_quiet(uint32_t quiet, bool activity, uint32_t sample_ms) {
    return activity ? 0u : quiet + sample_ms;
}

// Sleep is eligible only once the quiet window reached the trip-end threshold.
inline bool should_sleep(uint32_t quiet, uint32_t trip_end_ms) {
    return quiet >= trip_end_ms;
}

}  // namespace autobrain
