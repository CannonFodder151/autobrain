# AutoBrain firmware — phone-free trip logging PoC

Two firmware paths for phone-dead trip capture (GoFar parity). This is the CTO-org
deliverable from [AUT-369](/AUT/issues/AUT-369). Hardware sourcing + prototype
board is the BDM/Nathan track.

| Path | Status | Cost/unit | Compile-verified |
|---|---|---|---|
| [`esp32-diy/`](esp32-diy/) | Primary PoC — ESP32 + MCP2551/SN65HVD230 + DS3231 RTC + 12V buck + BLE | US$15–30 | ✅ (`pio run`, self-check passes) |
| [`freematics-one-plus/`](freematics-one-plus/) | Reference — Freematics ONE+ Model B, open Arduino SDK | US$135 | reference only (needs Freematics SDK) |

## Design principles (both paths)

Deterministic-first, AI-free on the edge: hardware signals decide everything,
nothing is left to inference.

1. **Ignition detect** — CAN bus responds to an OBD PID probe (and/or ACC pin high) ⇒ ignition ON. Sustained silence for `TRIP_END_MS` ⇒ OFF.
2. **Trip capture** — while ON, sample RPM + speed every second, append a CSV row to on-board flash (LittleFS) / SD. No phone, no network needed.
3. **Low power** — when OFF, deep-sleep and wake only on a timer (re-probe) or ACC GPIO edge. Target 10 µA–1 mA so the always-on 12V feed never drains the car battery.
4. **BLE sync** — PoC exposes the trip index over BLE; full file transfer is the app-side sync phase.

## Row schema (shared by both paths)

```
epoch,rpm,speed,coolant,throttle
```
One row per second while the engine is on. `epoch` is UTC from the DS3231
(battery-backed) RTC; without it the timestamps are junk, which is why the RTC
is non-negotiable on the DIY board.

## Build & verify (DIY path)

```sh
# host logic self-check (no Arduino needed)
cd firmware/esp32-diy/test && g++ -std=c++11 self_check.cpp -o self_check && ./self_check

# firmware build
cd firmware/esp32-diy && pio run
```

## Flash

```sh
cd firmware/esp32-diy && pio run -t upload && pio device monitor
```

Then power from a 5V bench supply (or the OBD pin 16 via the buck). Serial prints
`ignition ON/OFF` and `trip ended` so the state machine is observable on a bench
without a car (simulate "ignition" by injecting CAN traffic / raising ACC).

## Parts (DIY board) — BOM

| Part | Purpose | Approx cost |
|---|---|---|
| ESP32 dev board (ESP32-WROOM) | MCU, TWAI CAN on-die, BLE, LittleFS | US$5–8 |
| MCP2551 or SN65HVD230 | CAN transceiver (0–24V tolerant bus side) | US$1–3 |
| DS3231 + battery | battery-backed RTC for epoch timestamps | US$2–3 |
| 12V→5V DC-DC buck (e.g. MP1584) | always-on OBD power, survives crank dips | US$1–2 |
| Voltage divider + OBD-2 female plug | ACC sense + bus tap | US$1–3 |

See the full research memo + component table in the Outline doc
_2026-W33 OBD Dongle Research (AUT-363)_.
