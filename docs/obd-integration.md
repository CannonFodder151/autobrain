# AutoBrain OBD Port Integration — Next Steps

Live OBD-II logging via a Bluetooth OBD2 adapter is an in-progress roadmap item for the Android & iPhone apps. The backend/API seam and a "Work in progress" UI already landed; this page captures the plan and next steps (mirror of the Outline doc).

## Phone-free trip logging (firmware PoC)

See [`README.md`](https://github.com/CannonFodder151/autobrain-obd2-diy) and `DECISION.md` in the private firmware repo `CannonFodder151/autobrain-obd2-diy` for the full build-vs-buy picture (AUT-363 research → AUT-369 firmware PoC). Short version: ESP32 DIY board (US$15–30) with TWAI CAN + DS3231 RTC captures phone-dead trips to on-board flash; Freematics ONE+ (US$135) is the reference buy path. Firmware is written and compile-verified for the DIY path.

## Goal

Allow a user with an admin-enabled account to plug in a Bluetooth OBD2 adapter and log drives automatically into the AutoBrain logbook, read the VIN (auto-filling the vehicle if missing), and capture fault codes that can be pushed into the existing diagnostic AI tool.

## Vision

- **Generic OBD2 scanner companion**: rebrand a generic ELM327 / OBDLink type adapter with *continuous logging* and *auto power-off*, then white-label it.
- **Bluetooth auto-connect**: the app pairs with the adapter on start when `obd_auto_connect` is enabled.
- **Admin-gated**: an account can only use OBD when `obd_enabled` is set (admin toggle / admin API).
- **Logbook tie-in**: drive duration, distance and start/end odometer auto-populate a logbook trip (work/private).

## What already exists (this change-set)

Backend (`backend/app/api/v1/obd.py`, `/vehicles/{id}/obd`):

- `GET /settings` → `{enabled, auto_connect}` from the user record.
- `POST /vin` → auto-populate the vehicle VIN if missing.
- `GET|POST /codes`, `PATCH|DELETE /codes/{id}` → save fault codes; a button pushes codes into the existing diagnostics AI.
- `User.obd_enabled` / `User.obd_auto_connect` + admin toggle and `X-Admin-API-Key` support.

Frontend (`frontend/lib/screens/obd/obd_screen.dart`): "Work in progress" banner + codes library, VIN autofill, auto-connect switch, admin-gate lock screen.

## What exists now (mobile app — AUT-272)

`autobrain-mobile` (private repo, split from `frontend/`):

- **`lib/services/obd/elm327.dart`** — pure-Dart ELM327/OBD-II protocol layer (transport-agnostic): AT init, mode 01 PID decode (10 live PIDs incl. RPM/speed/coolant/MAF/throttle), supported-PID probing, mode 03/07 DTC decode with a deterministic code→meaning table, mode 09 VIN decode. Unit-tested (`test/elm327_test.dart`) against captured adapter replies — no hardware needed.
- **`lib/services/obd/obd_bt_transport.dart`** — Bluetooth Classic SPP transport via `flutter_bluetooth_serial_plus` (AGP-8-compatible fork; the original 0.4.0 package lacks `namespace` and fails modern Gradle builds). Android only — iOS has no public Bluetooth Classic.
- **`lib/services/obd/obd_connection.dart`** — connection lifecycle (enable BT, list bonded devices, connect, init session, remember last adapter in prefs for auto-connect).
- **`lib/screens/obd/obd_screen.dart`** — live connect card: adapter picker (bonded list), connect/disconnect, live PID chips (polled every 2 s), "Read fault codes" (mode 03+07 → saved to backend, deduped), auto VIN autofill on first connect, auto-connect when `obd_auto_connect` is on. Existing codes library + "Diagnose with AI" retained.
- Android manifest gained `BLUETOOTH`/`BLUETOOTH_ADMIN` (≤API 30) + `BLUETOOTH_CONNECT`/`BLUETOOTH_SCAN`.

Verified: `flutter analyze` clean for OBD files, `flutter test` 25 passing, debug APK builds.

## Next steps (mobile app)

1. **Adapter + protocol** — pick a generic ELM327/OBDLink adapter supporting logging and sleep-on-idle; log standard OBD-II PIDs; validate the (non-universal) odometer PID per make; plan dashboard-photo OCR / manual entry fallbacks.
2. **Bluetooth transport** — Android: Bluetooth Classic SPP/RFCOMM (ELM327 serial profile) ✅ shipped. iOS: Bluetooth Classic is not public; use a BLE ELM327 (UART GATT) — the key platform divergence.
3. **Realtime logging to logbook** — background sampling on Android; ignition-on starts a trip, ignition-off completes it (time, GPS, odo, distance).
4. **VIN + fault codes** — read VIN (mode 09) on first connect ✅ shipped; read DTCs (mode 03/07) ✅ shipped, save, and offer "Diagnose with AI".
5. **Account gating** — read `/obd/settings`; show lock screen when `!enabled` ✅ shipped.

## Risks / notes

- iOS has no Bluetooth Classic — a BLE (or Wi-Fi/CAN bridge) adapter is required for iPhone.
- The odometer PID is not universal — validate per make/model; keep the photo-OCR and manual fallbacks.
- ELM327 adapters are widely cloned with varying firmware — test auto-sleep per unit.
- Prefer adapters with sleep-on-idle / auto-off to avoid battery drain.

## Trip routes on the map (AUT-395)

Headline OBD2-port feature: drives recorded with GPS (the phone car-kit path, or
the DIY board's NEO-8M GPS later via BLE sync) render their route in the logbook.
Deterministic — raw `lat,lon` samples → polyline, no AI.

- Storage: `logbook_entries.gps_samples` JSON — `[{"t": epoch, "lat": deg, "lon": deg}]`.
- Ingestion: the board CSV `epoch,...,lat,lon` (raw degrees x10^7, `0,0` = no fix)
  is a valid source via `backend/app/services/trip_gps.py::parse_board_csv`;
  the phone path sends samples on the trip PATCH.
- Render: logbook trip detail → `GET /vehicles/{id}/logbook/{entry_id}` → flutter_map
  route; `0,0`/out-of-range samples dropped server-side.


## Definition of done

- Bluetooth auto-connect on app open when enabled.
- A single drive produces a logbook trip (start/end time, GPS, odo, distance, work flag) with no manual entry.
- VIN autofill when missing on first connect.
- Fault codes saved and one-tap into AI diagnostics.
- Works on both Android (SPP) and iPhone (BLE adapter); admin-gated per account; adapters sold white-labelled with logging + auto-off.