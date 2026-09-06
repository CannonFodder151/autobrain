# AutoBrain OBD2 Dongle — Build Docs

Build documentation for the custom AutoBrain OBD2 dongle: a phone-free trip
logger that plugs into the car's OBD-II port and records trips (time, RPM,
speed, GPS route) to on-board flash with no phone and no network.

**⚠️ Choose the guide that matches your devkit board:**

| Doc | What's in it | Board |
|---|---|---|
| [`nodemcu32s-build-guide.md`](nodemcu32s-build-guide.md) | **Primary guide** — BOM, pin map, soldering, flash, bench test | **NodeMCU-32S** (AliExpress linked in AUT-2741) |
| [`archive/03-soldering-guide.md`](archive/03-soldering-guide.md) | Archived DOIT-style soldering guide | **DOIT WROOM-32 devkit** (old) |
| [`archive/02-wiring.md`](archive/02-wiring.md) | Archived DOIT-style pin map | **DOIT WROOM-32 devkit** (old) |
| [`archive/01-bom.md`](archive/01-bom.md) | Archived BOM (migrated into `nodemcu32s-build-guide.md`) | — |
| [`archive/04-flash-and-test.md`](archive/04-flash-and-test.md) | Archived flash/test (migrated into `nodemcu32s-build-guide.md`) | — |
| [`archive/build-guide.md`](../firmware/esp32-diy/docs/archive/build-guide.md) | Archived firmware build pointer | — |

Firmware source: [`firmware/esp32-diy/`](../../firmware/esp32-diy/) (pin map in
`include/config.h` — the guide must match it).

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
