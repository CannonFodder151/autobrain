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
- **GPS power follows ignition** — the NEO-8M is powered (via `GPS_PWR_PIN`,
  GPIO14 → 2N7000) only while `run_trip()` is live, and cut in
  `sleep_until_ignition()`. This keeps the module's ~60–70 mA acquisition draw
  and its idle/NMEA current out of the always-on feed entirely. A GPS fix with
  speed ≥ `GPS_MOVE_KPH` also counts as trip activity, so a phone-dead trip
  stays open (and closes when the car stops) even on a CAN-less/ACC-less wiring
  variant.

## Sleep current budget (target)

| Rail | Active | Deep sleep |
|---|---|---|
| ESP32 (with BLE off, `esp_deep_sleep_disable_rom_logging`) | ~40 mA | ~10 µA |
| MCP2551/SN65HVD230 transceiver | ~5 mA | ~10 µA in standby (`CAN_STBY_PIN` high, `gpio_hold`) |
| **NEO-8M GPS (VIN cut by GPIO14 + 2N7000 in deep sleep)** | **~60–70 mA (only while trip is live)** | **0 µA (unpowered)** |
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
- **GPS power gate:** NEO-8M VCC via a 2N7000 (D → module VCC, S → GND, G →
  GPIO14, 10 kΩ gate-to-GND). Firmware drives `GPS_PWR_PIN` HIGH only during a
  trip. If the gate is unwired, set `GPS_PWR_PIN -1` in `config.h` — the module
  then stays powered all the time (accept the ~10–20 mA idle in sleep).

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
- **T6 — GPS fix + sleep budget with GPS off:** power the board on a bench with
  ACC high (so a trip starts) and the external antenna near a window.
  1. Confirm serial prints `GPS powered — wait for fix`; expect lat/lon in the
     CSV rows (nonzero, plausible) within ~30–60 s of lock and `sats` framing.
  2. Drive the polyline quality check: perturb/simulate speed via RMC; verify
     `kph10`/`course10` remain sane and rows stay within `SAMPLE_MS`.
  3. Drop ACC + stop CAN and let the trip close (`trip ended — sleeping`); re-run
     the T1 µA measurement and confirm the deep-sleep figure returns to budget
     (~0.2–1 mA) **with the NEO-8M unpowered** — i.e. the GPS gate holds it off.
  4. Test bench-benefit: with `GPS_PWR_PIN` unwired to a live module (VCC on
     3.3 V), expect sleep current to jump by the module's idle draw (~10–20 mA)
     — confirming why the gate matters.

Pass = T1–T6 all behave as specified. Record serial captures + current
readings against this plan on the issue.

## Sources

- `src/gps_neo8m.h` — NEO-8M driver: GGA/RMC NMEA ingest, fix/sats/speed/course
- `src/sleep_heuristics.h` — pure trip-gating (activity resets quiet window)
- `src/power.h` — deep-sleep prepare, wake-cause log, standby hold, GPS gate
- `src/main.cpp` — state machine wiring (BLE radio only while capturing, GPS
  powered only while capturing)
- `test/self_check.cpp` — gating invariants + NMEA parser checks
