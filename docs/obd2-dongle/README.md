# AutoBrain OBD2 Dongle — Build Docs

Build documentation for the custom AutoBrain OBD2 dongle: a phone-free trip
logger that plugs into the car's OBD-II port and records trips (time, RPM,
speed, GPS route) to on-board flash with no phone and no network.

**Board this is written for: the ESP32-WROOM-32 DevKit.** The CAN decoder is
built into the WROOM chip itself (Espressif calls it **TWAI**) — the firmware
talks to it directly via `driver/twai.h`. You do **not** buy or solder an
external CAN decoder/controller (no MCP2515, no SPI CAN board). The only CAN
part you buy is the small **transceiver** level-shifter (MCP2551 or
SN65HVD230), which is electrically required: no devkit pin may connect to the
car's ~12 V CAN bus directly.

## Contents

| Doc | What's in it |
|---|---|
| [`01-bom.md`](01-bom.md) | Exact shopping list, ~US$20–35 total |
| [`02-wiring.md`](02-wiring.md) | Full pin map + every wire between modules |
| [`03-soldering-guide.md`](03-soldering-guide.md) | **Step-by-step soldering guide** — order, checkpoints, smoke test |
| [`04-flash-and-test.md`](04-flash-and-test.md) | Flash the firmware, bench test, first car install |

Firmware source: [`firmware/esp32-diy/`](../../firmware/esp32-diy/) (pin map in
`include/config.h` — the docs here must match it).

## How it works (one paragraph)

The WROOM wakes on ignition (CAN bus activity or ACC 12 V via a divider),
samples RPM/speed over OBD-II once per second, appends GPS lat/lon from a
NEO-8M, and writes CSV rows (`epoch,rpm,speed,coolant,throttle,lat,lon`) to
LittleFS flash. When the engine goes off it closes the trip, deep-sleeps at
~0.2–1 mA (transceiver in standby, GPS unpowered), and uploads the trip over
WiFi/BLE later. Deterministic hardware signals decide everything — no AI on
the edge.

## Status

- Firmware: compile-verified (`pio run`) + host logic self-check passes.
- Hardware: BOM ordered; prototype build tracked in [AUT-386](/AUT/issues/AUT-386).
- Research memo: Outline doc _2026-W33 OBD Dongle Research (AUT-363)_.
