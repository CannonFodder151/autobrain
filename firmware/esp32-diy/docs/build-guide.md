# AutoBrain ESP32-DIY Dongle — Build Guide

**Moved.** The build guide was recreated from scratch in its own folder:

👉 [`docs/obd2-dongle/`](../../../docs/obd2-dongle/)

- [`README.md`](../../../docs/obd2-dongle/README.md) — overview + index
- [`01-bom.md`](../../../docs/obd2-dongle/01-bom.md) — exact parts list (~US$20–35)
- [`02-wiring.md`](../../../docs/obd2-dongle/02-wiring.md) — pin map + wiring
- [`03-soldering-guide.md`](../../../docs/obd2-dongle/03-soldering-guide.md) — step-by-step soldering
- [`04-flash-and-test.md`](../../../docs/obd2-dongle/04-flash-and-test.md) — flash + bench/car test

Key point for the ESP32-WROOM-32 DevKit: the CAN controller is on-chip
(**TWAI**, driven via `driver/twai.h`) — no external CAN decoder (MCP2515).
The MCP2551/SN65HVD230 is only the level-shifting **transceiver**.
