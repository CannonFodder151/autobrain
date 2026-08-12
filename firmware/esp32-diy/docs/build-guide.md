# AutoBrain ESP32-DIY Dongle — Build Guide (BOM + Soldering)

Firmware: `firmware/esp32-diy` (AUT-387 auto-sleep). Build the DIY OBD-II trip
logger from scratch. Full pin map in `include/config.h`.

## 1. What to buy (exact list)

All parts are AliExpress/eBay commodity items. Buy a 2-pack where cheaper; the
only functional requirements are in the "Need" column.

| # | Part | Exact thing to buy | Need | ~US$ |
|---|---|---|---|---|
| 1 | ESP32 dev board | ESP32-WROOM-32 devkit, 38-pin (DOIT-style, USB-C preferred) | MCU: CAN on-die (TWAI), BLE, LittleFS flash, deep sleep | 5–8 |
| 2 | CAN transceiver | **MCP2551** module (DIP-8 + breakout) OR **SN65HVD230** board. Must expose RS/STBY pin. | Level-shifts TWAI 3.3V ↔ OBD CAN 12V-tolerant bus | 1–3 |
| 3 | RTC module | **DS3231** module with CR2032 battery + holder pre-soldered | Battery-backed epoch timestamps (non-negotiable: no RTC = junk timestamps) | 2–3 |
| 4 | 12V→5V buck | **MP1584** (or MP2307) adjustable buck module, pre-made board | Always-on OBD power; survives crank dips; low no-load quiescent | 1–2 |
| 5 | OBD-II plug | OBD-II **male** plug with flying leads (or female plug + short cable) | Taps bus + 12V from the car's OBD port | 1–3 |
| 6 | Resistors | 1x each: 10 kΩ and 22 kΩ (1/4 W, any tolerance ≥5%) + 120 Ω for termination | ACC voltage divider (10k→GND, 22k→12V, tap at join = ~8V→GPIO15 safe); 120 Ω if you are the only/end node | ~1 |
| 7 | Protoboard + header pins | 8×6 cm perfboard, 2× 8-pin male headers, 2× 4-pin dupont shells or solder terminals | Mechanical mount + wire points | 2–4 |
| 8 | Hookup wire | 30 cm each: red, black, green, yellow, white | 12V, GND, CAN-H, CAN-L, ACC sense | ~2 |
| 9 | (Opt) OBD extension cable | OBD-II 16-pin male↔female extension | Bench-testing without the car | 3–6 |

**Total: ~US$15–30.** Skip #9 if bench-testing on a bench PSU (see test plan).

## 2. Pin map (firmware expects this — do not change without editing config.h)

| Signal | ESP32 pin | Notes |
|---|---|---|
| CAN TX | GPIO5 | → transceiver TXD/RXD side (DI) |
| CAN RX | GPIO4 | ← transceiver RXD (RO) |
| CAN STBY | GPIO18 | → transceiver RS/STBY pin (MCP2551 pin 8, SN65HVD230 pin 1). Hold high during deep sleep for ~10 µA standby |
| I2C SDA | GPIO21 | → DS3231 SDA |
| I2C SCL | GPIO22 | → DS3231 SCL |
| ACC sense | GPIO15 | ← divider tap, active HIGH (pulled down by 10 kΩ in firmware `INPUT_PULLDOWN`) |
| 5V | 5V/VBUS | from buck output |
| GND | GND | common ground with buck + transceiver + RTC |

## 3. Soldering — step by step

Work in this order. Solder the power rail first and verify with a multimeter
before any IC lands.

**3.1 Power rail (buck)**
1. Set the MP1584 output to 5.0 V **before wiring to anything**: power the buck
   input from a bench 12 V supply, tune the trimmer pot while measuring the
   output, then power it off.
2. Solder buck **IN+ / IN−** to the OBD plug leads for **pin 16 (12V, red)** and
   **pin 4 (chassis GND, black)**. Do not wire pin 16 to the ESP32 directly.
3. Solder buck **OUT+ (5V, red)** and **OUT− (GND, black)** to the ESP32 5V and
   GND pins.
4. Multimeter check: power the plug side from 12 V and confirm 5 V at the ESP32
   pin with nothing else connected. Wrong voltage here kills every board.

**3.2 CAN transceiver**
1. Solder 8-pin header, mount transceiver on perfboard.
2. **To ESP32:** TXD(DI) → GPIO5, RXD(RO) → GPIO4, RS/STBY → GPIO18, VCC → 5V,
   GND → GND.
3. **To OBD:** CANH → plug lead for **pin 6 (CAN-H, green)**, CANL → plug lead
   for **pin 14 (CAN-L, yellow)**.
4. If this board is the only node on the bus (bench, or a car where you're the
   only tap), solder **120 Ω between CANH and CANL**. Skip if the car already
   terminates (most do — verify by checking ~60 Ω across pins 6/14 with car
   unplugged).
5. Continuity check: ESP32 GPIO5 ↔ transceiver DI, GPIO4 ↔ RO, no shorts to GND.

**3.3 RTC (DS3231)**
1. Solder 4-pin header. Wire **SDA → GPIO21, SCL → GPIO22, VCC → 5V, GND → GND**.
2. Insert CR2032 (this is what keeps the clock alive while the car is off).
3. Note: DS3231 modules pull SDA/SCL to 3.3 V or 5 V depending on the module;
   the ESP32 GPIOs are 5 V-tolerant on 21/22. If your module is 3.3 V-only, wire
   VCC to the 3.3 V pin instead.

**3.4 ACC sense divider** — the 12 V ignition-sense feed must be divided down
to a logic level safe for ESP32 (3.3 V logic, but GPIO15 is 5 V-tolerant).
1. Solder **33 kΩ (12V side) + 10 kΩ (GND side)**, tap the junction to GPIO15:
   tap = 2.79 V @ 12 V (engine off), 3.35 V @ 14.4 V (charging) — above
   logic-high, never over 5 V tolerance.
2. Firmware pulls GPIO15 down (`INPUT_PULLDOWN`), so the divider is the
   active-HIGH `ACC_PIN` sense.

**3.5 Assembly + smoke test**
1. Mount everything, shrink-wrap or hot-glue so nothing touches the metal case.
2. Before plugging into a car, bench-test with a **12 V bench PSU** (never the
   car first): see `docs/auto-sleep.md` test plan T1–T5.
3. First real install: plug in with engine off, watch serial — expect
   `ignition OFF — sleeping` and sleep current near budget (~0.2–1 mA).

## 4. Flash

```sh
cd firmware/esp32-diy && pio run -t upload && pio device monitor
```

## 5. Sleep current budget (after assembly)

| Rail | Deep sleep |
|---|---|
| ESP32 (BLE off, ROM logging off) | ~10 µA |
| CAN transceiver (RS held high) | ~10 µA |
| DS3231 + CR2032 | µA (battery-backed) |
| MP1584 no-load quiescent | ~0.2–1 mA |
| **Total** | **≈ 0.2–1 mA @ 12 V** |

Measure with a µA meter in series with the plug's 12 V lead. If you see more
than ~1 mA, check: transceiver RS wired to GPIO18, buck set to 5 V (not 12 V
passthrough), no LED modules left powered on the 5 V rail.
