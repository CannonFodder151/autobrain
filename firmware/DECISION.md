# Phone-free trip logging — build vs buy decision (firmware PoC, AUT-369)

Status: **firmware PoC shipped** — DIY path compile-verified, Freematics reference written.
Decision gate is the hardware demo on a car (needs Nathan's prototype board).

## Recommendation (interim)

**DIY board first.** It is the only path that reaches GoFar parity at US$18–35/unit
and the firmware is now written + build-verified. Freematics ONE+ (US$135) remains
the buy-path reference: proven SDK, no PCB work, but 4–9× the per-unit cost.

| Criterion | ESP32 DIY (US$18–35) | Freematics ONE+ B (US$135) | Hybrid (iCar Pro + app) |
|---|---|---|---|
| Phone-dead trip capture | ✅ on-board LittleFS | ✅ on-board SD | ❌ dies with phone |
| GPS route logging | ✅ NEO-8M (lat/lon per row) | ✅ built-in GPS | ❌ (app GPS, dies with phone) |
| Cost/unit (product scale) | **US$18–35** | US$135 | +$25 adapter + app |
| Time to MVP (firmware) | 2–4 mo | 2–4 mo (SDK faster) | — (app-only) |
| Effort | PCB + solder + firmware | buy + flash | app work only |
| RTC (epoch accuracy) | DS3231 add-on | built-in | phone RTC |
| Low-power deep sleep | 10µA–1mA target, done | ~10mA sleep | N/A (phone) |
| Cert/compliance | DIY burden | dev platform only | N/A |
| Production path | custom, ~500+ units | per-unit at scale | immediate |

## Firmware scope delivered

- `firmware/esp32-diy/` — TWAI CAN ignition detect → OBD-II PID sampling (RPM/speed)
  → GPS position logging (NEO-8M lat/lon per row) → LittleFS CSV per trip →
  DS3231 RTC epochs → deep sleep (timer + ACC GPIO wake) → BLE service advertising
  trip index. **Compile-verified** (PlatformIO) + host self-check
  (`test/self_check.cpp`) for the pure PID/CSV/NMEA/RTC logic.
- `firmware/freematics-one-plus/` — SDK-accurate reference sketch for Model B
  (COBD + SDLogger). Needs the Freematics SDK to build; reference only.
- Row schema `epoch,rpm,speed,coolant,throttle,lat,lon` shared by both paths so the app
  sync code is written once.

## Remaining to close the decision (hardware in hands)

1. Nathan: prototype the DIY board (PCB + MCP2551 + DS3231 + NEO-8M + buck) — 1–2 wks.
2. Bench-validate: simulated CAN/ACC on the dev box, verify trip file + deep sleep current.
3. Car test: phone-dead trip on a real drive; compare DIY vs Freematics capture.
4. Gate: DIY wins if capture + power targets hold; else Freematics or hybrid.

## What the firmware intentionally does NOT do yet (PoC ceiling)

- Full BLE file transfer (index-only now) — add when the app sync client exists.
- Fuel/odo/DTC logging, GNSS track, trip classification — Phase 2 backlog.
- Deep-sleep current is *targeted*, not yet *measured* — measurement needs the board.
