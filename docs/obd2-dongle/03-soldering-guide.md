# AutoBrain OBD2 Dongle — Soldering Guide

Step-by-step build for the ESP32-WROOM-32 based OBD2 dongle. Work top to
bottom — each stage ends in a **checkpoint** you must pass before the next
stage. Total build time: 2–3 hours first time.

Pin references: [`02-wiring.md`](02-wiring.md). Parts: [`01-bom.md`](01-bom.md).

---

## 0. Tools & consumables

- Soldering iron, 350–380 °C, fine tip (conical or small chisel)
- 60/40 or SAC305 rosin-core solder, 0.6–0.8 mm
- Multimeter (continuity beep + DC volts)
- Side cutters, wire strippers, flush tweezers
- Helping-hands / PCB vise
- Isopropyl alcohol + old toothbrush (flux cleanup)
- Optional but recommended: bench 12 V supply (a laptop brick + barrel plug works)

---

## 1. Prep

1. Check every module on the bench: NEO-8M LED blinks on 3.3 V, DS3231 shows
   on I2C scan, buck trim pot turns freely. Dead parts are easier to return
   unsoldered.
2. Cut perfboard to fit all modules with ~1 cm spare: 8×6 cm is enough.
3. Tin every wire end (strip 3 mm, twist, feed solder into strands).
4. Plan layout dry-fit before any solder:

```
┌─────────────────────────────────────────────┐
│ [Buck]        [2N7000 + resistors]          │
│                                             │
│ [ESP32-WROOM devkit — center, headers up]   │
│                                             │
│ [MCP2551/HVD230]   [DS3231]     [NEO-8M]    │
└─────────────────────────────────────────────┘
```

Keep the GPS antenna socket facing outward/away from the transceiver and buck
(switching noise). Leave a path to route the antenna lead out of the case.

**Checkpoint:** layout fits, nothing overlaps, OBD cable exits cleanly.

---

## 2. Stage A — Buck preset (no board work yet)

1. Bench 12 V onto buck IN+/IN−.
2. Multimeter on OUT+: turn the trim pot until it reads **5.00 V ± 0.05 V**.
3. Power off. Mark the pot position with paint pen so vibration can't be
   mistaken later.

**Checkpoint:** 5.00 V measured. Do not skip — an unverified buck at 12 V
passthrough kills the WROOM, RTC, and GPS instantly.

## 3. Stage B — Mount the ESP32 devkit

1. Solder the two 8-pin male header strips to the **perfboard**, not the
   devkit, so the devkit stays socketed/removable.
2. Seat the devkit on the headers. Do **not** solder devkit to headers yet.

**Checkpoint:** devkit plugs in/out; pins align with your layout plan.

## 4. Stage C — Power rail first

1. Solder OBD plug red → buck IN+, black → buck IN−. Route these away from
   where GPIO wiring will live.
2. Solder buck OUT+ → the devkit's **5V** header row; OUT− → GND row.
3. Solder one spare black GND wire as the board's common-ground bus point.

**Checkpoint (power gate):**
- 12 V on plug ⇒ 5.00 V at devkit 5V pin.
- Continuity: plug black ↔ devkit GND < 1 Ω.
- No continuity between 5V and GND (beep test must stay silent).

Only after this checkpoint do ICs get soldered.

## 5. Stage D — CAN transceiver

Option A (MCP2551): socket it DIP-8 style; wire per `02-wiring.md` §MCP2551 —
TXD→GPIO5, RXD via the 1 k/2 k divider→GPIO4, RS→GPIO18, VDD→5V, VSS→GND,
CANH→green, CANL→yellow.

Option B (SN65HVD230): breakout board, VCC→**3.3V**, D→GPIO5, R→GPIO4 direct,
RS→**GPIO18**, CANH/CANL to green/yellow.

1. Solder the four logic wires short (<5 cm) and routed together.
2. Solder green/yellow CAN leads from the OBD plug to CANH/CANL pads.
3. If termination needed (see `02-wiring.md`), solder 120 Ω across CANH/CANL
   now.

**Checkpoint:** continuity GPIO5↔TXD, GPIO4↔RXD(-divider), GPIO18↔RS;
CANH↔green lead, CANL↔yellow lead; no shorts CANH↔CANL unless the 120 Ω is
fitted (~120 Ω reading).

## 6. Stage E — DS3231 RTC

1. Solder 4-pin header on perfboard, seat module.
2. Wire SDA→GPIO21, SCL→GPIO22, VCC→3.3V rail, GND→GND.
3. Insert CR2032 (+ side up on ZS-042).

**Checkpoint:** continuity SDA↔21, SCL↔22; resistance SDA-to-3.3V ≈ few kΩ
(module pullups); battery reads ~3 V in holder.

## 7. Stage F — ACC divider

Solder directly between points, keep leads <3 cm:
33 kΩ from OBD red (+12 V node) → tap point; 10 kΩ from tap → GND; white wire
from tap → GPIO15.

**Checkpoint:** tap-to-GND = 10 kΩ; tap-to-12V-node = 33 kΩ; no solder bridge
to neighbours.

## 8. Stage G — GPS + power gate + antenna

1. 4-pin header for NEO-8M; wire TX→GPIO16, RX→GPIO17, VCC→3.3 V rail.
2. 2N7000 low-side gate per `02-wiring.md`: module **GND** → drain, source →
   board GND, gate → GPIO14 with 10 kΩ gate-to-GND pulldown. Get drain/source
   right — 2N7000 body diode conducts source→drain if reversed and the "off"
   state will back-feed ~half-supply through the diode.
3. Clip external antenna onto IPX socket (push straight down, it's fragile).
4. Route antenna lead away from buck + CAN pair.

**Checkpoint:** gate LOW (GPIO14 unpowered) ⇒ NEO-8M GND floats (no continuity
module-GND to board-GND). Gate pulled to 3.3 V ⇒ continuity closes. Module VCC
reads 3.3 V, never 5 V.

## 9. Stage H — Final sweep before power

1. Flux cleanup: IPA + toothbrush, air dry.
2. Magnifier pass over every joint: dull/cracked/bridged joints reflow now.
3. Beep sweep: every adjacent header pair on the devkit must NOT beep unless
   both nets are GND.
4. Socket-check: devkit still unplugged? Good — smoke test comes next.

## 10. Smoke test (first power-up)

1. Devkit seated, everything else connected, USB **not** plugged.
2. 12 V onto the OBD plug.
3. Watch for: no heat spots, no smell, current draw roughly tens of mA
   (devkit LEDs on).
4. Measure: 5 V at devkit ✓, 3.3 V at 3V3 pin ✓, NEO-8M VCC 3.3 V ✓, ACC tap
   ≈0 V (ignition off) ✓.
5. Now flash firmware (`04-flash-and-test.md`), open serial monitor, and only
   then touch the car.

---

## Common mistakes (read before powering)

| Mistake | Symptom | Prevention |
|---|---|---|
| Buck left at 12 V passthrough | Instant dead WROOM | Stage A preset + paint mark |
| NEO-8M VCC on 5 V | Dead GPS | 3.3 V only, checkpoint in Stage G |
| MCP2551 RXD straight to GPIO4 | Stressed/dead GPIO over time | 1 k/2 k divider |
| 2N7000 drain/source swapped | GPS never fully off | Body-diode check in Stage G |
| Missing gate pulldown | GPS wakes during boot glitch | 10 kΩ gate-to-GND |
| DS3231 powered 5 V | SDA/SCL pulled to 5 V | Power module from 3.3 V |
| Cold joints on header rows | Intermittent resets on car vibration | Magnifier pass, Stage H |
| CAN pair twisted loosely near buck | Bus errors | Twist green+yellow, keep off buck |
