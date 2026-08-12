# esp32-diy auto-sleep when car off

Auto-sleep so the always-on OBD 12V feed never drains the car battery.
Requirement: [AUT-387](/AUT/issues/AUT-387) (addendum to the 2026-W33 OBD
Dongle Research, 11 Aug 2026).

## Design

Sleep/wake is a pure hardware state machine — no AI, no inference:

```
                 +---------------------- deep sleep --------------------+
                 |                                                      |
   ACC high / CAN alive  ->  run_trip()   --TRIP_END_MS silence-->  sleep
                 ^                                                      |
                 +-------- wake: ACC GPIO high (instant) or             |
                              SLEEP_CHECK_MS timer (CAN-only cars) -----+
```

- **Car-off detect** — the trip loop closes only after `TRIP_END_MS` (45s) of
  sustained silence (no CAN PID responses, ACC low). That closing is what makes
  sleep eligible (`sleep_heuristics.h`).
- **Wake on car-on** — two paths: ACC pin high via GPIO level wake (instant
  catch of engine start) and a `SLEEP_CHECK_MS` (2 min) timer re-probe for cars
  that only wake CAN on ignition and never pull an ACC line.
- **Sleep only between trips** — the quiet accumulator resets on any activity
  (`next_quiet`), so sleep can never fire mid-log; invariants are unit-tested in
  `test/self_check.cpp`.

## Sleep current budget (target)

| Rail | Active | Deep sleep |
|---|---|---|
| ESP32 (with BLE off, `esp_deep_sleep_disable_rom_logging`) | ~40 mA | ~10 µA |
| MCP2551/SN65HVD230 transceiver | ~5 mA | ~10 µA in standby (`CAN_STBY_PIN` high, `gpio_hold`) |
| DS3231 + coin cell | µA | µA (RTC battery-backed) |
| 12V→5V buck no-load quiescent | ~0.2–1 mA | ~0.2–1 mA (MP1584-class) |
| **Total** | | **≈ 0.2–1 mA** |

1 mA at 12V ≈ 12 mW. A typical 60 Ah battery with, say, a 0.5 Ah budget for
the dongle gives weeks-to-months parked; the dominant cost is the buck's
no-load quiescent, not the ESP32.

## Wiring (new)

- Wire the CAN transceiver **RS** pin (MCP2551 pin 8 / SN65HVD230 pin 1) to
  **GPIO18** and set `CAN_STBY_PIN` in `config.h` (default 18; `-1` if unwired).
- ACC divider to GPIO15 as before (active HIGH).

## Bench test plan (hardware not yet in hand — do this when the board arrives)

Setup: bench PSU simulating OBD pin 16 (12V), a 5V rail, ACC on a spare GPIO or
a button, and either a CAN traffic generator or nothing (ACC-only fallback
path). Serial at 115200.

- **T1 — boot, car off:** power on with ACC low and no CAN traffic.
  Expect `wake cause: boot/power-on`, `ignition OFF — sleeping`. Verify deep
  sleep: quiescent current ≈ budget (measure series µA). Expect the timer probe
  (`wake cause: timer`) every `SLEEP_CHECK_MS` and a return to sleep.
- **T2 — wake on ACC:** with the board asleep, raise ACC.
  Expect `wake cause: gpio (ACC high)` then `ignition ON — capturing trip`.
- **T3 — wake on CAN:** add a CAN-only car simulation: never raise ACC, inject
  RPM/speed responses to PID 0x0C/0x0D. Expect wake by timer probe, trip
  starts, rows append every `SAMPLE_MS`.
- **T4 — trip closes on silence:** stop injecting CAN and drop ACC.
  Expect ~`TRIP_END_MS` later `trip ended — sleeping`, then `wake cause: timer`
  probes with no trip restarts. Confirm the trip CSV on LittleFS has one
  header + only the active window's rows (no mid-log gaps, no phantom rows).
- **T5 — standby transceiver:** with `CAN_STBY_PIN` wired, compare sleep
  current with RS held high vs low; confirm the standby figure lands near the
  µA budget (T1 re-run).

Pass = T1–T5 all behave as specified. Record serial captures + current
readings against this plan on the issue.

## Sources

- `src/sleep_heuristics.h` — pure trip-gating (activity resets quiet window)
- `src/power.h` — deep-sleep prepare, wake-cause log, standby hold
- `src/main.cpp` — state machine wiring (BLE radio only while capturing)
- `test/self_check.cpp` — gating invariants
