# AutoBrain OBD2 Dongle — NodeMCU-32S Build Guide

This is the **current** build guide for the AutoBrain OBD2 dongle using a
**NodeMCU-32S** ESP32 devkit (the AliExpress board you linked). If you have a
DOIT-style WROOM devkit instead, see `archive/03-soldering-guide.md` (archived).

> ✅ **This board.** NodeMCU-32S = ESP32-WROOM-32 module + CH340 USB-UART + 38-pin
> header, USB-C or micro-USB. The on-die **TWAI** CAN controller is built into the
> WROOM chip — you do **not** buy or solder an external CAN decoder (no MCP2515).
> The only CAN part you solder is the **transceiver** (MCP2551), which level-shifts
> 3.3 V ↔ car CAN 12 V.

## Table of contents

1. [Parts list](#1-parts-list)
2. [NodeMCU-32S board reference](#2-nodemcu-32s-board-reference)
3. [Pin-out at a glance](#3-pin-out-at-a-glance)
4. [What to solder where](#4-what-to-solder-where)
   - 4.1 [Power chain — buck converter + OBD2 plug](#41-power-chain--buck-converter--obd2-plug)
   - 4.2 [CAN transceiver (MCP2551, 6-pin DIP)](#42-can-transceiver-mcp2551-6-pin-dip)
   - 4.3 [RTC — DS3231 (I²C)](#43-rtc--ds3231-i2c)
   - 4.4 [GPS — NEO-8M + power gate (2N7000)](#44-gps--neo-8m--power-gate-2n7000)
   - 4.5 [ACC ignition sense](#45-acc-ignition-sense)
   - 4.6 [BRO-8 (ESP-01 breakout) — power + serial passthrough](#46-bro-8-esp-01-breakout--power--serial-passthrough)
5. [Step-by-step soldering](#5-step-by-step-soldering)
6. [Smoke test (first power-up)](#6-smoke-test-first-power-up)
7. [Flash & verify](#7-flash--verify)
8. [Troubleshooting](#8-troubleshooting)

Firmware: [`firmware/esp32-diy/`](../../firmware/esp32-diy/). Pin map:
`include/config.h` (change there if you deviate — docs must match).

---

## 1. Parts list

| # | Part | Exact thing to buy / notes |
|---|------|---------------------------|
| 1 | ESP32 dev board | **NodeMCU-32S** (ESP32-WROOM-32 module + CH340, 38-pin header) |
| 2 | CAN transceiver | **MCP2551** DIP-8 (6 usable pins: VCC, GND, TXD, RXD, CANH, CANL; RS is pin 8) |
| 3 | RTC module | **DS3231** module with CR2032 coin cell + holder |
| 4 | DC-DC buck | **MP1584** / MP2307 adjustable buck (12 V → 5 V) |
| 5 | OBD-II plug | Male OBD-II plug, flying leads (or female + extension) |
| 6 | GPS module | **NEO-8M** (U-blox, ceramic patch, IPX/U.FL) OR **NEO-7M** (3.3 V, also fine) |
| 7 | GPS antenna | External active/patch antenna, IPX/U.FL connector |
| 8 | GPS power switch | **2N7000 N-MOSFET** (one per module) + 10 kΩ pulldown |
| 9 | Resistors | **22 kΩ**, **10 kΩ**, **33 kΩ**, **120 Ω** (1/4 W, ≥5%) |
| 10 | BRO-8 | ESP-01 breakout board (8-pin: VCC, RST, CH_PD/EN, GPIO0, TX, RX, GND, NC) |
| 11 | Level shift | **2N7000** (second one for BRO-8 TX↔RX) or 4-channel I²C level shifter |
| 12 | Perfboard | 8×6 cm, 2× 8-pin male headers (socket the ESP devkit, don't solder it) |
| 13 | Hookup wire | 30 cm each: red, black, green, yellow, white, blue, orange |

**You already have:** 22k, 10k, 33k resistors, 2N7000 MOSFETs, buck converter, OBD2
plug, MCP2551 (6-pin), DS3231, BRO-8. You need: NodeMCU-32S (linked), NEO-8M,
antenna, perfboard, wire, 120Ω resistor.

---

## 2. NodeMCU-32S board reference

The NodeMCU-32S has **38 pins** in two rows along each side of the board. The
silkscreen labels printed next to each hole are your friend — match by label, not
position, because clones vary.

**Board layout** (USB connector at bottom, ESP-WROOM-32 module at top — antenna
sticking out the top edge):

```
    Left column (toward USB-C/micro):           Right column (toward module):

       3V3   ┌────┐                             ┌────┐  D23
       GND   │ESP32│                             │    │  D22   ← I2C SCL (GPIO22)
       D34   └────┘                             └────┘  D21   ← I2C SDA (GPIO21)
       D35                                    D27/D26   GND
       D32                                    D14/D12   D15   ← ACC sense (GPIO15)
       D33                                    D13/D0    D2    (onboard LED)
       D25                                    D1      D16     ← RX2 (GPIO16)
       D26                                    D25(5)  D17     ← TX2 (GPIO17)
       D27                                    D14     D18     ← CAN STBY (GPIO18) ← see note
       D14   ← GPS PWR (GPIO14)                D18  D19
       D12                                    D23     D5  ← CAN TX (GPIO5)
       D13                                    D12    GND
       D0                                     D13    D4  ← CAN RX (GPIO4)
       D1                                     D15    D15  (see below, ACC)
       D16  ← RX2 (GPIO16)                    D27    TX0  (GPIO1, USB serial — leave alone)
       D17  ← TX2 (GPIO17)                    D26   RX0  (GPIO3, USB serial — leave alone)
       D18  ← CAN STBY (GPIO18)               D25   3V3
       D19                                    D34   EN
       D23  ← (also HSPI MOSI, avoid)         D35   D0
       GND                                   GPIO6–11 = flash, DO NOT USE
       VIN   ← 5V from buck                    (GPIO6–11 soldered to flash chip under shield)
```

### 🔴 Critical: GPIO 6–11 are flash pins — DO NOT USE
The ESP32-WROOM-32 module has its flash chip soldered to GPIO6–11 internally. On
the NodeMCU-32S these pins are not broken out (they're under the metal shield).
If you see them exposed on a rogue clone label, **do not solder to them** — the
board won't boot.

### GPIO numbers vs pin labels (NodeMCU-32S)
The NodeMCU-32S prints **Dxx** on the silkscreen. The actual ESP32 GPIO number
differs. Here's the exact mapping you need:

| Silkscreen label | ESP32 GPIO | Your use |
|---|---|---|
| D21 | GPIO21 | DS3231 SDA |
| D22 | GPIO22 | DS3231 SCL |
| D15 | GPIO15 | ACC ignition sense |
| D14 | GPIO14 | GPS power gate (2N7000 gate) |
| D18 | GPIO18 | CAN transceiver RS (standby) |
| D5  | GPIO5  | CAN TX (to transceiver TXD) |
| D4  | GPIO4  | CAN RX (from transceiver RXD) |
| TX2 | GPIO17 | NEO-8M RX |
| RX2 | GPIO16 | NEO-8M TX |
| D19 | GPIO19 | BRO-8 TX (software serial RX) |
| D23 | GPIO23 | BRO-8 RX (software serial TX) |
| D16 | GPIO16 | Alternative GPS RX2 (if TX2/RX2 used for BRO-8) |

### Strapping pins (GPIO 0, 2, 12, 15)
- **GPIO15 (D15)**: pulled **LOW** at boot via internal pulldown. The ACC divider
  holds it high when ignition is on — firmware handles this. Safe.
- **GPIO14 (D14)**: not a strapping pin on ESP32 (it's GPIO 14 / SPI CLK on some
  flash modes, but on NodeMCU it's just a general GPIO). The 2N7000 gate pulldown
  keeps GPS off during boot glitches. Safe.
- **GPIO4, 5, 18, 21, 22, 16, 17**: no strapping constraints.

---

## 3. Pin-out at a glance

This table is the **single source of truth**. All solder connections below are
derived from it. The firmware (`config.h`) is already set for these pins — do
not change code unless you deviate.

| Signal | ESP32 GPIO | NodeMCU-32S label | Direction | Component / wire |
|--------|-----------|-------------------|-----------|-----------------|
| CAN TX | 5 | D5 | → out | MCP2551 TXD |
| CAN RX | 4 | D4 | ← in | MCP2551 RXD (via divider) |
| CAN STBY | 18 | D18 | out | MCP2551 RS (pin 8) |
| SDA | 21 | D21 | bidir | DS3231 SDA |
| SCL | 22 | D22 | out | DS3231 SCL |
| ACC | 15 | D15 | in | ACC divider tap |
| GPS TX | 17 | TX2 | → out | NEO-8M RX |
| GPS RX | 16 | RX2 | ← in | NEO-8M TX |
| GPS PWR | 14 | D14 | out | 2N7000 gate #1 |
| BRO-8 RX | 19 | D19 | ← in | BRO-8 TX |
| BRO-8 TX | 23 | D23 | → out | BRO-8 RX |
| BRO-8 PWR | — | — | out | 2N7000 gate #2 (3.3 V gate) |
| 5V rail | — | VIN | in | Buck OUT+ |
| 3.3 V rail | — | 3V3 | out | DS3231, NEO-8M, BRO-8 |
| GND | — | GND | — | Everything common |

> ⚠️ **ESP32 GPIOs are 3.3 V logic — NOT 5 V-tolerant.** The BRO-8 (ESP-01) runs
> at 3.3 V too, so level shifting is only needed for the TX direction to be safe
> if BRO-8's VCC ends up at 3.3 V (it will be — see §4.6).

---

## 4. What to solder where

> 🔧 **Reference:** all resistor values below match what you have — 22k, 10k, 33k,
> 120Ω. All MOSFETs are 2N7000. Two of them (one for GPS gate, one for BRO-8 gate).

---

### 4.1 Power chain — buck converter + OBD2 plug

```
OBD-II pin 16 (+12 V) ──────────→ Buck IN+  (red wire)
OBD-II pin 4  (GND)   ──────────→ Buck IN−  (black wire)

Buck OUT+ (≈5.0 V) ─────────────→ NodeMCU-32S VIN / 5V pin
Buck OUT− (GND)    ─────────────→ NodeMCU-32S GND
```

**Before powering anything:** set the buck to exactly **5.00 V**
(±0.05 V). Apply 12 V to the buck input, adjust the trim pot, measure output.
Mark the pot with a paint pen. An unverified buck at 12 V passthrough kills the
WROOM, DS3231, and GPS instantly.

---

### 4.2 CAN transceiver — MCP2551 (6-pin DIP)

Your MCP2551 has 6 pins exposed (the 8-pin DIP has 2 NC pins). Here's the pinout:

**MCP2551 pinout (8-pin DIP, you use 6):**

```
           ┌─────────┐
  TXD  (1) │  ○   ○  │ (8)  VDD
  VSS  (2) │  ○   ○  │ (7)  CANH
  VDD  (3) │  ○   ○  │ (6)  CANL
  RXD  (4) │  ○   ○  │ (5  VREF
           └─────────┘
  RS  (8)  ← top, left when pin 1 dot at top-left
```

> Pin 8 = RS (standby). Pin 5 = VREF (leave floating). The 6 pins you connect:
> TXD (1), VSS (2), VDD (3), RXD (4), CANH (7), CANL (6), RS (8).

| MCP2551 pin | Name | Solder to |
|---|---|---|
| 1 | TXD (data in) | NodeMCU-32S **D5** (GPIO5) |
| 2 | VSS | GND (buck OUT− / board GND) |
| 3 | VDD | 5 V rail (buck OUT+) |
| 4 | RXD (data out) | **22kΩ + 10kΩ divider** → D4 (GPIO4) |
| 5 | VREF | Leave floating (unconnected) |
| 6 | CANL | OBD-II **pin 14** (yellow wire) |
| 7 | CANH | OBD-II **pin 6** (green wire) |
| 8 | RS (standby) | NodeMCU-32S **D18** (GPIO18) |

#### The RXD voltage divider (MCP2551 RXD → GPIO4)

MCP2551 RXD idles at VDD = 5 V. The ESP32 GPIO4 max is 3.3 V. Use the 22k + 10k
resistors you already have:

```
MCP2551 RXD ──┬────────────────────── D4 (GPIO4)
              │
            [22k]              ← 22kΩ resistor (you have this value)
              │
            [10k]              ← 10kΩ resistor (you have this value)
              │
            GND
```

Voltage at D4 when RXD=5 V: 5 V × 10k/(22k+10k) = **1.61 V** LOW-side tap...
**correct this**: the divider is 22k on top (from RXD), 10k on bottom (to GND).

```
RXD (5 V) ──[22k]──●──[10k]── GND
                   │
                 D4 (GPIO4)
```

Voltage at D4 = 5 V × (10k / (22k + 10k)) = 5 × 0.3125 = **1.56 V** when HIGH.

That's **too low** for a reliable 3.3 V logic HIGH (ESP32 VIH = 0.8 × 3.3 = 2.64 V
min for "sure", but 0.5 × 3.3 = 1.65 V is the absolute minimum).

**Use 22k on top + 33k on bottom:**

```
RXD (5 V) ──[22k]──●──[33k]── GND
                   │
                 D4 (GPIO4)
```

Voltage = 5 V × (33k / (22k + 33k)) = 5 × 0.6 = **3.0 V**. Solid HIGH. ✅

**Solder this divider:** 22kΩ from MCP2551 pin 4 → a join point; 33kΩ from that
join → GND; a wire from the join → D4. Keep leads <3 cm.

---

### 4.3 RTC — DS3231 (I²C)

The DS3231 module is a small blue PCB (ZS-042 style) with 4 pins: VCC, GND, SDA,
SCL. It usually has onboard 4.7 kΩ I²C pullups to VCC.

| DS3231 pin | Solder to |
|---|---|
| VCC | **3.3 V rail** (NodeMCU-32S 3V3) — NOT 5 V, or the pullups drag SDA/SCL to 5 V |
| GND | GND |
| SDA | D21 (GPIO21) |
| SCL | D22 (GPIO22) |

Insert the CR2032 coin cell **+ side up** (printed on the holder).

---

### 4.4 GPS — NEO-8M + power gate (2N7000)

The NEO-8M module pins (typical 6-pin): VCC, GND, TX, RX, IPX/U.FL, (sometimes
another VCC or NC).

| NEO-8M pin | Solder to |
|---|---|
| VCC | 3.3 V rail (NodeMCU-32S 3V3) |
| GND | 2N7000 **drain** (low-side switch) |
| TX | RX2 (GPIO16) |
| RX | TX2 (GPIO17) |
| IPX/U.FL | External antenna lead |

#### 2N7000 low-side power gate (GPS)

This cuts the NEO-8M's ground path in deep sleep (~60–70 mA saved):

```
                NodeMCU-32S D14 (GPIO14)
                       │
                    [gate]
                       │
                 2N7000 N-MOSFET
                       │
                [drain] │ [source]  ← body diode points source→drain
                       │
NEO-8M GND ──────┬─────┴───────────── Board GND (buck OUT−)
              [10k]
                 │
              GND
```

| 2N7000 pin | Wire |
|---|---|
| Gate (G) | D14 (GPIO14) |
| Drain (D) | NEO-8M GND pin |
| Source (S) | Board GND |
| (Between gate and GND) | 10kΩ pulldown |

**Gate HIGH** (GPIO14 = 3.3 V) → FET conducts → GPS ground path complete → GPS
powered.
**Gate LOW** (GPIO14 = 0 V, deep sleep) → pulldown holds off → GPS ground floats
→ GPS draws 0 µA.

Pinout of 2N7000 (TO-92 package, flat side facing you, legs down):

```
   G  D  S
  ( ) ( )( )
   │  │  │
  G  D  S
```

**Body diode matters:** the 2N7000 has an intrinsic diode from source to drain.
If you reverse D and S, the "off" state back-feeds ~1.5–2 V through the diode
and the GPS never fully powers off. **Drain → GPS GND, Source → board GND.**

#### External antenna
Clip the IPX/U.FL antenna onto the NEO-8M socket. Push straight down — the
connector is fragile. Route the antenna lead away from the buck converter and
CAN pair (switching noise / EMI). Run it up to the windscreen/dash top.

---

### 4.5 ACC ignition sense

Two resistors: you have **33k** and **10k**.

```
OBD-II pin 16 (+12 V) ──[33k]──●──[10k]── GND

                         │
                         │
                    D15 (GPIO15)
```

Voltage at D15 when pin 16 = 12.6 V: 12.6 × 10k/(33k+10k) = 12.6 × 0.233 =
**2.93 V** → logic HIGH (VIH min = 2.64 V). ✅
At 14.4 V (charging): 14.4 × 0.233 = **3.35 V** → still safe (ESP32 abs max = 3.6 V). ✅

Firmware configures GPIO15 as `INPUT_PULLDOWN`, so when the car is off (or the
wire is disconnected) it reads LOW.

---

### 4.6 BRO-8 (ESP-01 breakout) — power + serial passthrough

The BRO-8 board has 8 pins: VCC, Rx, Tx, GND (and 4 more for ESP-01: RST, EN,
GPIO0, GPIO1 — but your board only exposes VCC/Rx/Tx/GND). It runs at 3.3 V.

**Power the BRO-8 from the 3.3 V rail** via a 2N7000 switch (same as GPS gate
approach) — this lets firmware cut BRO-8 power in deep sleep to save ~15 mA:

```
                NodeMCU-32S D25 (GPIO25)   ← or any free GPIO
                       │
                    [gate]
                       │
                 2N7000 N-MOSFET (2nd one)
                       │
                [drain] │ [source]
                       │
BRO-8 VCC ───────┬─────┴────────────── 3.3 V rail (NodeMCU-32S 3V3)
           [10k] │
              GND

BRO-8 GND ───────→ board GND (direct)
```

Wait — BRO-8 VCC comes from 3.3 V. If we low-side switch ground instead:

```
3.3 V rail ───────→ BRO-8 VCC (direct)
BRO-8 GND  ────────●── 2N7000 drain
                   │
                 Source ── board GND
                 Gate ── NodeMCU-32S D25 (GPIO25) + 10k pulldown
```

This is the **low-side gate** for BRO-8 (cut its ground return). Gate HIGH → BRO-8
powered; Gate LOW → BRO-8 off.

#### Serial passthrough (BRO-8 TX → ESP32 D19 / GPIO19, BRO-8 RX → ESP32 D23 / GPIO23)

The ESP32's hardware UART0 is the USB serial (GPIO1/3). Don't clobber it.
Use **software serial** on D19 (RX, from BRO-8 TX) and D23 (TX, to BRO-8 RX).

```
BRO-8 TX ───────→ D19 (GPIO19)   ← ESP32 reads BRO-8 data
BRO-8 RX ───────→ D23 (GPIO23)   ← ESP32 sends data to BRO-8
              [22k]                    ↑
BRO-8 TX ────●──[divider]── D19          │
        [10k]  (optional, see below)      │
        GND                              3.3 V logic — BRO-8 TX is 3.3 V, no divider needed if BRO-8 VCC = 3.3 V
```

> ✅ **No level shifter needed** if BRO-8 runs at 3.3 V (it will, since we power it
> from the 3V3 rail). The 2N7000 MOSFETs you have are **not needed for BRO-8
> level shifting** — they're for power gating. The serial lines are 3.3 V ↔ 3.3 V.

---

## 5. Step-by-step soldering

Work **bottom-up** on perfboard. Each stage ends in a checkpoint.

### Tools needed
- Soldering iron, 350–380 °C, fine chisel/conical tip
- 60/40 or SAC305 rosin-core, 0.6–0.8 mm
- Multimeter (continuity beep + DC volts)
- Side cutters, wire strippers, flush tweezers, helping hands
- Isopropyl alcohol + toothbrush
- Bench 12 V supply (a laptop brick + barrel works)

### Layout plan (dry-fit first)

```
┌───────────────────────────────────────────┐
│  [Buck]  [2× 2N7000]  [resistor bank]    │
│                                           │
│  [NodeMCU-32S devkit — center, USB out]   │
│                                           │
│  [MCP2551]     [DS3231]     [NEO-8M+ant]  │
│  [BRO-8]                                   │
└───────────────────────────────────────────┘
```

Keep the GPS antenna socket pointing outward, away from the buck and transceiver.

---

### Stage A — Buck preset (no board connected)
1. 12 V onto buck IN+/IN−.
2. Trimpot until OUT reads **5.00 V** (±0.05 V).
3. Power off. Paint-pen the pot position.

**Checkpoint:** 5.00 V verified.

### Stage B — Mount the NodeMCU-32S
Socket the devkit on two 8-pin header strips soldered to perfboard (don't solder
the devkit itself — keep it removable).

**Checkpoint:** devkit plugs in/out cleanly.

### Stage C — Power rails
1. Red wire: OBD-II pin 16 → buck IN+.
2. Black wire: OBD-II pin 4 → buck IN−.
3. Buck OUT+ → NodeMCU-32S **VIN** (or 5V pin — they're the same rail).
4. Buck OUT− → GND bus.

**Checkpoint:** 12 V in → 5.00 V at VIN pin. No 5 V↔GND short (beep stays silent).

### Stage D — CAN transceiver (MCP2551)
1. DIP-8 socket or direct-solder the MCP2551.
2. Pin 1 (TXD) → D5 (GPIO5).
3. Pin 2 (VSS) → GND.
4. Pin 3 (VDD) → 5 V rail.
5. Pin 4 (RXD) → **22k/33k divider** → D4 (GPIO4).
6. Pin 5 (VREF) → floating.
7. Pin 6 (CANL) → OBD-II pin 14 (yellow).
8. Pin 7 (CANH) → OBD-II pin 6 (green).
9. Pin 8 (RS) → D18 (GPIO18).
10. **120Ω termination**: solder across CANH–CANL **only if** your car doesn't
    already have one. Most cars do — measure 60 Ω across pins 6–14 with the
    car OFF and plug out; if you read ~60 Ω, skip the 120 Ω. If you read open
    circuit, add the 120 Ω between MCP2551 pin 7 (CANH) and pin 6 (CANL).

**Checkpoint:** GPIO5↔TXD ✓, GPIO4↔RXD-via-divider ✓, GPIO18↔RS ✓, CANH↔green ✓,
CANL↔yellow ✓. No CANH↔CANL short (unless 120 Ω fitted).

### Stage E — DS3231 RTC
1. 4-pin header on perfboard; seat the module.
2. VCC → 3.3 V rail.
3. GND → GND.
4. SDA → D21 (GPIO21).
5. SCL → D22 (GPIO22).
6. CR2032 inserted (+ up on the holder).

**Checkpoint:** SDA↔21 ✓, SCL↔22 ✓, battery reads ~3 V.

### Stage F — ACC divider
22k + 10k divider as in §4.5:
- 33k from OBD red (+12 V node) → tap.
- 10k from tap → GND.
- White wire from tap → D15 (GPIO15).

**Checkpoint:** tap-to-GND = 10k, tap-to-12V = 33k, no bridge.

### Stage G — GPS + power gate + antenna
1. NEO-8M: VCC → 3.3 V, GND → 2N7000 drain, TX → RX2, RX → TX2, IPX → antenna.
2. 2N7000 #1 (GPS gate): G → D14 (GPIO14), S → GND, D → NEO-8M GND.
3. 10k pulldown: G ↔ GND.
4. Antenna: push IPX connector straight down.

**Checkpoint:** D14 low (unpowered) → NEO-8M GND floats (no continuity to board
GND). D14 high → continuity closes. NEO-8M VCC = 3.3 V, never 5 V.

### Stage H — BRO-8 + power gate + serial
1. BRO-8 VCC → 3.3 V rail (direct).
2. BRO-8 GND → 2N7000 #2 drain.
3. 2N7000 #2: G → **D25 (GPIO25)**, S → board GND, 10k pulldown G↔GND.
4. BRO-8 TX → D19 (GPIO19).
5. BRO-8 RX → D23 (GPIO23).

**Checkpoint:** D25 low → BRO-8 off (no continuity GND-GND). D25 high → powered.
BRO-8 TX↔D19 ✓, BRO-8 RX↔D23 ✓.

### Stage I — Final sweep
1. IPA + toothbrush flux cleanup; air dry.
2. Magnifier pass: no dull/bridged/cold joints.
3. Beep-sweep: every adjacent header pair must NOT beep unless both are GND.
4. USB still unplugged — we power from OBD.

---

## 6. Smoke test (first power-up)

1. Devkit seated, USB **not** plugged in.
2. 12 V onto the OBD-II plug.
3. Watch for: no heat, no smell, current draw ~ tens of mA (devkit LEDs on).
4. Measure: 5 V at VIN ✓, 3.3 V at 3V3 ✓, NEO-8M VCC = 3.3 V ✓, ACC tap ≈ 0 V
   (ignition off) ✓.

**If anything is hot/smells: power off immediately, re-check buck output and
all 5 V→3.3 V wiring.**

---

## 7. Flash & verify

```sh
cd firmware/esp32-diy
pio run -t upload
pio device monitor       # 115200 baud
```

Expected boot banner (car off):
```
AutoBrain-Tripper v0.2.0 boot — wake cause: boot/power-on
ignition OFF — sleeping
```

Then it deep-sleeps. The full state machine:
[`../firmware/esp32-diy/docs/auto-sleep.md`](../../firmware/esp32-diy/docs/auto-sleep.md)

### Bench test (no car)
| Check | How | Pass |
|---|---|---|
| Rail voltages | multimeter | 5.0 V at VIN, 3.3 V at 3V3 |
| Sleep current | µA meter in series with 12 V lead | ≈0.2–1 mA after "sleeping" |
| GPS gate | measure NEO-8M GND in sleep | 0 V / open (off) |
| Transceiver standby | compare µA with RS high vs GND | ~10 µA delta |

### Simulate ignition
Jumper 3.3 V to the ACC divider tap (D15) **or** inject CAN frames:
- Frame ID `0x7DF`, data `[0x02, 0x01, 0x0C]` (RPM request).

Serial should show:
```
ignition ON — capturing trip
GPS powered — wait for fix (antenna near window)
```

---

## 8. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No 5 V at ESP32 | Buck not preset, or OBD pins 16/4 swapped | Re-run Stage A |
| Board brownout loops in car | Buck sags under load | Reset to 5.00 V, check wiring gauge |
| No CAN responses | Transceiver unpowered, RXD divider wrong, no termination | Check MCP2551 VDD=5 V, divider 22k/33k, 120 Ω if open circuit |
| RXD divider gives wrong voltage | Wrong resistor ratio | Use 22k (top) + 33k (bottom) → 3.0 V at 5 V input |
| GPS never fixes | IPX antenna unseated, or module at 5 V (dead) | Reseat antenna, power GPS from 3.3 V only |
| GPS won't power off | 2N7000 D/S reversed | Drain→GPS GND, Source→board GND |
| DS3231 not found | SDA/SCL swapped, or VCC absent | Check 3.3 V power, swap SDA/SCL |
| BRO-8 won't boot | VCC not gated, or GND switch reversed | Verify 2N7000 #2 wiring |
| Sleep current >1 mA | GPS/BRO-8 gate leak, transceiver RS unwired | Check all FET body diodes, RS→GPIO18 |
| CANH↔CANL short | 120 Ω fitted but car already terminated | Remove 120 Ω if car has 60 Ω across pins 6–14 |
