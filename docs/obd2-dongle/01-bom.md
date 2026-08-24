# AutoBrain OBD2 Dongle — Bill of Materials

All parts are AliExpress/eBay commodity items. Buy a 2-pack where cheaper.
The "Need" column is the functional requirement; pick any vendor that meets it.

<!-- omit latex -->
| # | Part | Exact thing to buy | Purpose | ~US$ |
|---|------|-------------------|---------|------|
| 1 | ESP32 dev board | **ESP32-WROOM-32 devkit, 38-pin (DOIT-style, USB-C preferred)** | MCU: CAN on-die (TWAI), BLE, LittleFS flash, deep sleep | 5–8 |
| 2 | CAN transceiver | **MCP2551** module (DIP-8 + breakout) OR **SN65HVD230** board. Must expose RS/STBY pin. | Level-shifts WROOM's 3.3 V TX/RX ↔ OBD CAN 12 V | 1–3 |
| 3 | RTC module | **DS3231** module with CR2032 battery + holder pre-soldered | Battery-backed UTC timestamps for offline logging | 2–3 |
| 4 | DC-DC buck | **MP1584** (or MP2307) adjustable buck, pre-made board | Always-on 12 V from OBD pin 16 → 5 V for ESP32; survives crank dips | 1–2 |
| 5 | OBD-II plug | OBD-II **male** plug with flying leads (or female plug + short cable) | Taps pin 16 (+12 V), pin 4 (GND), CAN-H, CAN-L | 1–3 |
| 6 | GPS module | **NEO-8M** module (U-blox NEO-8M, ceramic patch + IPX footprint) | Trip route: lat/lon + speed/course per row | 3–5 |
| 7 | GPS antenna | **External active/patch GPS antenna with wire lead + IPX/U.FL connector** (≈25×25 mm patch with 3.3 V LNA) | Reliable under-dash fix; OBD area blocks tiny ceramic patch | 2–4 |
| 8 | GPS power switch | 2N7000 N-MOSFET (or NPN) + 10 kΩ gate pulldown | Cuts NEO-8M VIN off in deep sleep (~60–70 mA acquisition draw gone) | ~1 |
| 9 | Resistors | **1x 33 kΩ**, **1x 10 kΩ**, **1x 120 Ω** (1/4 W, ≥5% tolerance) | ACC 12 V divider to logic level; CAN termination | ~1 |
| 10 | Protoboard & headers | 8×6 cm perfboard, 2× 8-pin male headers, 2× 4-pin dupont shells or solder terminals | Mechanical mount for all modules | 2–4 |
| 11 | Hookup wire | 30 cm each: red, black, green, yellow, white | 12 V (red), GND (black), CAN-H (green), CAN-L (yellow), ACC (white) | ~2 |
| 12 | OBD extension (opt) | OBD-II 16-pin male↔female extension | Bench-testing without the car | 3–6 |

**Total: ~US$20–35**

Skip #12 if bench-testing with a 12 V supply first (recommended).

---

## Important notes

- **Item #1 is the only one with CAN on-die.** The WROOM's TWAI controller means
  you do **not** need or solder an external CAN decoder (MCP2515, MCP2551 in SPI mode).
- **Item #2 is transceiver only.** It only shifts levels from 3.3 V to ~12 V on the bus.
  Its RS/STBY pin must be wired to GPIO 18 for deep-sleep standby.
- **Accelerometer on WROOM devboards:** many cheap DOIT devkits include a built-in
  1.5–2 V accelerometer on GPIO 36. Leave it unconnected unless the code uses it.