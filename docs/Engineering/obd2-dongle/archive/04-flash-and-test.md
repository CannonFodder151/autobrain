# AutoBrain OBD2 Dongle — Flash & Test

Flashing, bench test without a car, then first install. Serial outputs shown
match `firmware/esp32-diy/src/main.cpp`.

Pin map: [`02-wiring.md`](02-wiring.md) · Parts: [`01-bom.md`](01-bom.md)

---

## 1. Host logic self-check (no hardware needed)

```sh
cd firmware/esp32-diy/test
g++ -std=c++11 self_check.cpp -o self_check
./self_check
```

All invariants pass = CSV/NMEA/RTC logic is sound before touching hardware.

## 2. Flash the firmware

```sh
cd firmware/esp32-diy
pio run -t upload          # devkit on USB; hold BOOT if the upload won't sync
pio device monitor         # 115200 baud
```

Expected boot banner with car off:

```
AutoBrain-Tripper v0.2.0 boot — wake cause: boot/power-on
ignition OFF — sleeping
```

Then the board deep-sleeps. Wake causes print as `timer` (2-min re-probe) or
`gpio` (ACC high). Full state machine: [`../firmware/esp32-diy/docs/auto-sleep.md`](../../firmware/esp32-diy/docs/auto-sleep.md).

## 3. Bench test (12 V PSU, no car)

| Check | How | Pass |
|---|---|---|
| Rail voltages | multimeter | 5.0 V at 5V pin, 3.3 V at 3V3 pin |
| Sleep current | µA meter series with 12 V lead | ≈0.2–1 mA after `sleeping` prints |
| GPS gate holds | measure NEO-8M VCC while "sleeping" | 0 V (module unpowered) |
| Transceiver standby | compare µA with RS high vs grounded | ~10 µA delta |

### Simulate ignition

Raise ACC (jumper 3.3 V to GPIO15 tap) **or** inject CAN traffic:

- Frame ID `0x7DF`, data `[0x02, 0x01, 0x0C]` (RPM request), repeated.

Serial should show:

```
ignition ON — capturing trip
GPS powered — wait for fix (antenna near window)
```

Rows append to LittleFS once per second while RPM/speed/ACC/GPS-motion is
present. Drop ACC + stop CAN → after `TRIP_END_MS` (45 s):

```
trip ended — WiFi upload window
upload done — sleeping
```

### GPS fix check

Antenna lead near a window. First fix: under a minute warm, a few minutes cold
(ceramic-patch-under-metal would never lock — that's why the external antenna
is BOM item #7). Rows carry nonzero `lat,lon`; `0,0` = no fix yet.

## 4. WiFi upload provisioning (optional, AUT-918)

1. AutoBrain app → **Settings → Dongle** → enable WiFi upload.
2. App creates the device, you pick the vehicle.
3. Pair over BLE (`AutoBrain-Tripper`) within the 2-minute parked window; the
   app pushes `{ssid, pass, api_url, device_id, api_key}` — first-write-only,
   stored in NVS. Factory reset to re-provision.
4. Completed trips upload over TLS with backoff; retries are idempotent.

No soldering involved — all pins stay as wired.

## 5. Car install

1. **Engine OFF:** plug into the OBD-II port. Expect the boot banner then
   `ignition OFF — sleeping`. Repeated brownout reboots ⇒ buck output sagging;
   re-verify 5.0 V under load before continuing.
2. **Ignition ON (engine off):**
   ```
   AutoBrain-Tripper v0.2.0 boot — wake cause: ...
   ignition ON — capturing trip
   ```
3. **Start engine:** RPM/speed values climb in rows; GPS fixes as antenna sees
   sky. Drive normally.
4. **Ignition OFF:** ~45 s later `trip ended`, board sleeps at ≈0.2–1 mA —
   safe to leave plugged in permanently.

## 6. Verify trip data

Trips land in LittleFS as CSV and surface in the app logbook via BLE/WiFi sync.
Row schema (shared with the app parser):

```
epoch,rpm,speed,coolant,throttle,lat,lon,soc_pct,pack_v,pack_a,pack_temp_c,odo_km,ev_mode
1700000000,750,0.0,98.5,12.0,-338687241,1512109053
```

`epoch` UTC from DS3231 · `lat,lon` degrees ×10⁷ signed WGS84, `0,0` when no
fix. Route renders in the logbook from the lat/lon pairs (AUT-395).

## 7. Troubleshooting

| Symptom | Likely cause |
|---|---|
| No 5 V at ESP32 | buck not preset, or plug pins 16/4 swapped |
| Board brownout loops in car | buck output sags under load — reset to 5.00 V |
| No CAN responses | transceiver unpowered, RXD divider missing (MCP2551), or termination missing on bench bus |
| GPS never fixes | IPX antenna unseated, or module fed 5 V (dead) |
| `WARN: DS3231 not found` | SDA/SCL swapped, or module VCC absent |
| Trip never ends | ACC line stuck high (divider shorted) |
| Sleep current >1 mA | GPS gate leak (drain/source swapped), transceiver RS unwired, buck quiescent high |
