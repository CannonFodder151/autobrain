# AutoBrain firmware — phone-free trip logging PoC

Two firmware paths for phone-dead trip capture (GoFar parity). This is the CTO-org
deliverable from [AUT-369](/AUT/issues/AUT-369). Hardware sourcing + prototype
board is the BDM/Nathan track.

**Build documentation** (BOM, wiring, soldering, flash/test) lives in its own
folder: [`docs/obd2-dongle/`](../docs/obd2-dongle/) — written for the
**ESP32-WROOM-32 DevKit** (CAN decodes on-chip via TWAI; the MCP2551/SN65HVD230
is only the level-shifting transceiver).

| Path | Status | Cost/unit | Compile-verified |
|---|---|---|---|
| [`esp32-diy/`](esp32-diy/) | Primary PoC — ESP32 + MCP2551/SN65HVD230 + DS3231 RTC + NEO-8M GPS (+ external antenna + power gate) + 12V buck + BLE, **WiFi trip auto-upload (AUT-918 + AUT-969 provisioning)** | US$20–35 | ✅ (`pio run`, self-check passes) |
| [`freematics-one-plus/`](freematics-one-plus/) | Reference — Freematics ONE+ Model B, open Arduino SDK | US$135 | reference only (needs Freematics SDK) |

## Design principles (both paths)

Deterministic-first, AI-free on the edge: hardware signals decide everything,
nothing is left to inference.

1. **Ignition detect** — CAN bus responds to an OBD PID probe (and/or ACC pin high) ⇒ ignition ON. Sustained silence for `TRIP_END_MS` ⇒ OFF.
2. **Trip capture** — while ON, sample RPM + speed every second, append a CSV row to on-board flash (LittleFS) / SD. No phone, no network needed.
3. **GPS position** — NEO-8M (UART2) adds lat/lon — plus speed/course from the
   RMC sentence — to every row, so every trip draws as a route in the logbook.
   Powered via a GPIO gate (`GPS_PWR_PIN`) so it's only live while capturing.
4. **Low power / auto-sleep** — when OFF, deep-sleep and wake only on ACC high or a timer re-probe. The CAN transceiver goes to standby (RS held high via `gpio_hold`) during sleep, GPS is unpowered (`GPS_PWR_PIN` low), BLE runs only while capturing, and the target quiescent draw is ~0.2–1 mA so the always-on 12V feed never drains the car battery. Full design + bench test plan in [`esp32-diy/docs/auto-sleep.md`](esp32-diy/docs/auto-sleep.md) (AUT-387 → AUT-917).
5. **BLE sync** — PoC exposes the trip index over BLE; full file transfer is the app-side sync phase.

## Row schema (shared by both paths)

```
epoch,rpm,speed,coolant,throttle,lat,lon,soc_pct,pack_v,pack_a,pack_temp_c,odo_km,ev_mode
```
One row per second while the engine is on. `epoch` is UTC from the DS3231
(battery-backed) RTC; without it the timestamps are junk, which is why the RTC
is non-negotiable on the DIY board. `lat,lon` are degrees ×10⁷ (signed; WGS84,
e.g. `-338687241,1512109053`), written when the NEO-8M has a fix — a consumer
draws the trip route on a map from the row pairs, skipping `0,0` rows. EV/PHEV
fields (`soc_pct`, `pack_v`, `pack_a`, `pack_temp_c`, `odo_km`, `ev_mode`) are
appended for new firmware; old 7-field rows are still accepted by the parser.

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

## Deep-sleep design

Full design + bench test plan in [`esp32-diy/docs/auto-sleep.md`](esp32-diy/docs/auto-sleep.md) (AUT-387 → AUT-917).

See the full research memo + component table in the Outline doc
_2026-W33 OBD Dongle Research (AUT-363)_.
