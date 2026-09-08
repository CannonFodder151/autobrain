# AutoBrain OBD2 Dongle — Pin Map & Wiring

Every wire between parts. Firmware expects exactly this mapping (`firmware/esp32-diy/include/config.h`); change code there if you deviate.

> ⚠️ ESP32 GPIOs are **3.3 V logic and not 5 V-tolerant**. Every wire leaving
> the WROOM must stay ≤3.3 V. This doc routes all car-side voltages through
> the buck, the divider, and the transceiver — never straight onto a GPIO.

---

## Master pin map

"Board label" is the silkscreen printed next to the header hole on the devkit
(see the [board locator](#board-locator-where-every-pin-sits-on-the-devkit) below).

| Signal | ESP32 pin | Board label | Direction | Connects to | Notes |
|--------|-----------|-------------|-----------|-------------|-------|
| CAN TX | GPIO 5 | **D5** | out | Transceiver TXD (data in) | strapping pin — see boot notes |
| CAN RX | GPIO 4 | **D4** | in | Transceiver RXD (data out) | see transceiver § — may need divider |
| CAN STBY | GPIO 18 | **D18** | out | Transceiver RS/STBY | HIGH in sleep ⇒ ~10 µA standby |
| I2C SDA | GPIO 21 | **D21** | bidir | DS3231 SDA | default I2C SDA |
| I2C SCL | GPIO 22 | **D22** | bidir | DS3231 SCL | default I2C SCL |
| ACC sense | GPIO 15 | **D15** | in | Divider tap | `INPUT_PULLDOWN`; HIGH = ignition on; strapping pin |
| GPS TX | GPIO 17 | **TX2** | out | NEO-8M RX | UART2 TX, 9600 baud |
| GPS RX | GPIO 16 | **RX2** | in | NEO-8M TX | UART2 RX, 9600 baud |
| GPS PWR | GPIO 14 | **D14** | out | 2N7000 gate | HIGH = GPS on; 10 kΩ gate-to-GND pulldown |
| 5 V rail | 5V/VBUS | **VIN** | in | Buck OUT+ | powers ESP32 + MCP2551 |
| 3.3 V rail | 3V3 | **3V3** | out | NEO-8M VCC, DS3231 VCC, GPS gate pullup side | never feed these 5 V |
| GND | GND | **GND** | — | everything | one common ground |

---

## Board locator — where every pin sits on the devkit

The BOM calls for a **38-pin DOIT-style ESP32-WROOM-32 devkit**. USB socket at
the bottom, metal shield/antenna at top. Left/right as seen looking at the
board with USB toward you:

```
            ┌─────────[ ESP32-WROOM-32 · antenna end ]─────────┐
       3V3 ─┤ LEFT                                        RIGHT ├─ D23
        EN ─┤                                             ├─ D22   ◄─ I2C SCL
        VP ─┤ (GPIO36, input-only)                        ├─ TX0   (GPIO 1 — USB serial, leave alone)
        VN ─┤ (GPIO39, input-only)                        ├─ RX0   (GPIO 3 — USB serial, leave alone)
       D34 ─┤ (input-only)                                ├─ D21   ◄─ I2C SDA
       D35 ─┤ (input-only)                                ├─ GND   ◄─ common ground
       D32 ─┤                                             ├─ D19
       D33 ─┤                                             ├─ D18   ◄─ CAN STBY
       D25 ─┤                                             ├─ D5    ◄─ CAN TX
       D26 ─┤                                             ├─ TX2   ◄─ GPS TX (GPIO 17)
       D27 ─┤                                             ├─ RX2   ◄─ GPS RX (GPIO 16)
       D14 ─┤ ◄─ GPS PWR                                  ├─ D4    ◄─ CAN RX
       D12 ─┤ (unused; must stay LOW at boot)             ├─ D0    (unused; flashing strap)
       D13 ─┤                                             ├─ D2    (unused; onboard LED)
       GND ─┤ ◄─ common ground                            ├─ D15   ◄─ ACC sense
       VIN ─┤ ◄─ 5 V in from buck                         ├─ GND   ◄─ common ground
            └──[ CLK · SD0 · SD1 · SD2 · SD3 · CMD ]──────┘
                 (GPIO 6–11 — wired to flash chip, DO NOT USE)
```

Every wire used by this build lands on the **right column except GPS PWR
(D14)**, which is on the left between D27 and D12.

> ⚠️ **Clones differ.** Some devkits are 30-pin (no 3V3 pin, no flash-pin row),
> some shuffle which edge the extra pins sit on. The silkscreen labels above
> (D5, TX2, VIN…) are identical across DOIT-style clones — always match the
> label printed next to the hole, not the position.

### Boot-time notes for the pins we use

These GPIOs are also **strapping pins** sampled at power-on. The build is
already compatible — don't "fix" them away:

- **D5 (CAN TX)**: must be HIGH at boot. The transceiver only *listens* on
  this line, so it can't pull it down. Safe.
- **D15 (ACC sense)**: LOW at boot just suppresses the serial boot log (ignition
  off = divider holds it low). HIGH at boot (ignition on) is the normal-boot
  state. Either way it boots.
- **D14 (GPS PWR)**: glitches high briefly during boot. The 10 kΩ gate pulldown
  keeps the 2N7000 off, so the GPS stays unpowered until firmware drives the
  pin — that's exactly why the pulldown is mandatory.
- **D4 / D18 / D21 / D22 / TX2 / RX2**: no boot constraints.

---

## OBD-II plug (male, facing the car)

| OBD pin | Function | Wire color | Goes to |
|---------|----------|------------|---------|
| 16 | Battery +12 V | red | Buck IN+ |
| 4 | Chassis GND | black | Buck IN− and board GND |
| 6 | CAN-H | green | Transceiver CANH |
| 14 | CAN-L | yellow | Transceiver CANL |
| 5 | Signal GND | — | optional: bond to pin 4 / board GND |

All other pins: leave unconnected.

**Termination:** most cars already terminate the bus (≈60 Ω across pins 6–14,
measured with the plug out of the car). Only if you measure open circuit AND
this dongle is the sole node: solder 120 Ω between CANH and CANL.

---

## Power chain

```
OBD pin 16 (+12V) ──► Buck IN+        Buck OUT+ (5.0 V) ──► ESP32 5V/VBUS
OBD pin 4  (GND)  ──► Buck IN−        Buck OUT− (GND)   ──► ESP32 GND
```

Set the buck to **5.0 V before anything else is connected** (bench 12 V in,
trim pot, multimeter on OUT). 5.0 V feeds the ESP32 devkit's onboard 3.3 V
regulator — never wire the buck output to the 3V3 pin.

---

## CAN transceiver (pick ONE)

### Option A — MCP2551 (5 V part, DIP-8)

| MCP2551 pin | Name | Connects to |
|-------------|------|-------------|
| 1 | TXD | ESP32 GPIO 5 |
| 2 | VSS | GND |
| 3 | VDD | 5 V |
| 4 | RXD | **divider** → ESP32 GPIO 4 |
| 5 | VREF | leave unconnected |
| 6 | CANL | OBD pin 14 (yellow) |
| 7 | CANH | OBD pin 6 (green) |
| 8 | RS (STBY) | ESP32 GPIO 18 |

RXD idles at VDD = 5 V, so divide it down before GPIO 4:

```
MCP2551 RXD ──[1 kΩ]──┬──[2 kΩ]── GND
                      │
                 GPIO 4  (≈3.3 V HIGH, 0 V LOW)
```

### Option B — SN65HVD230 (3.3 V part, SOIC-8 breakout)

| HVD230 pin | Name | Connects to |
|------------|------|-------------|
| 1 | D (TXD in) | ESP32 GPIO 5 |
| 2 | GND | GND |
| 3 | VCC | **3.3 V** (not 5 V!) |
| 4 | R (RXD out) | ESP32 GPIO 4 (direct — same logic level) |
| 5 | Vref | leave unconnected |
| 6 | CANL | OBD pin 14 |
| 7 | CANH | OBD pin 6 |
| 8 | RS (mode/stby) | ESP32 GPIO 18 |

No divider needed — RXD swings 0–3.3 V. Simpler build if buying fresh.

---

## DS3231 RTC

| DS3231 | Connects to |
|--------|-------------|
| VCC | **3.3 V** |
| GND | GND |
| SDA | GPIO 21 |
| SCL | GPIO 22 |

Powering the common ZS-042 module from 3.3 V keeps its onboard I2C pullups at
3.3 V — safe for the WROOM. (At 5 V those pullups drag SDA/SCL to 5 V.) The
chip runs fine at 3.3 V and the CR2032 still holds time with main power off.

---

## ACC ignition sense

```
OBD pin 16 (+12V) ──[33 kΩ]──●──[10 kΩ]── GND
                             │
                        GPIO 15
```

Tap ≈2.79 V @ 12 V, ≈3.35 V @ 14.4 V charging — solid logic HIGH, always under
the absolute-max rating. Firmware configures `INPUT_PULLDOWN`, so ignition-off
reads LOW even with the divider disconnected.

---

## NEO-8M GPS + power gate

| NEO-8M | Connects to |
|--------|-------------|
| VCC | 3.3 V (direct — the gate switches GND below) |
| GND | 2N7000 drain |
| TX | GPIO 16 |
| RX | GPIO 17 |
| IPX/U.FL socket | external antenna lead |

**Power gate — low-side 2N7000:**

```
NEO-8M VCC ────────────── 3.3 V (permanent)

GPIO14 ──[gate]          NEO-8M GND ──[drain] 2N7000 [source]── GND
              └── 10 kΩ gate-to-GND pulldown
```

Gate HIGH ⇒ FET conducts ⇒ module ground path complete ⇒ GPS powered (~60–70 mA
while acquiring). Gate LOW (deep sleep; pulldown holds it off) ⇒ module floats
⇒ 0 µA. The pulldown guarantees the GPS cannot power itself during reset/boot
glitches.

**Antenna:** clip the external patch/active antenna onto the module's IPX
socket, run the lead away from the CAN pair and the 12 V feed, up to dash top /
windscreen. Under-dash ceramic patches take minutes to first fix; a window-view
external patch locks in under a minute.
