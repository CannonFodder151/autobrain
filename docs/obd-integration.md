# AutoBrain OBD Port Integration — Next Steps

Live OBD-II logging via a Bluetooth OBD2 adapter is an in-progress roadmap item for the Android & iPhone apps. The backend/API seam and a "Work in progress" UI already landed; this page captures the plan and next steps (mirror of the Outline doc).

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

## What exists now (mobile app — AUT-362, auto trip recording)

VGate iCar Pro (passive ELM327 v1.5 BT-Classic bridge, no onboard storage) works as
a leave-in trip logger, GoFar-style, entirely app-side:

- **`lib/services/obd/obd_trip_recorder.dart`** — pure-Dart ignition-heuristic engine:
  fed battery voltage (mode 01 PID `0142`) + engine RPM (`010C`) + BT link state, it
  starts a logbook trip on ignition-on and closes it on ignition-off/link-drop, with
  hysteresis + debounce (no flapping at the 12.8-13.2 V band). The in-progress trip is
  buffered to SharedPreferences so a mid-drive app kill does not lose it, and finished
  trips queue for a retrying backend sync (`source=obd_auto` so users can tell them
  apart from manual entries). Unit-tested (`test/obd_trip_recorder_test.dart`).
- **`lib/services/obd/obd_trip_monitor.dart`** — singleton orchestrator: one 2 s poll
  loop feeds both the live PID screen and the recorder (no double Bluetooth traffic),
  auto-connects to the remembered adapter at app start, auto-reconnects with 30 s
  backoff, and treats a BT link-drop as ignition-off.
- **`lib/services/obd/obd_keepalive*.dart`** — Android foreground service
  (`connectedDevice`, via `flutter_foreground_task`) that keeps the app process alive
  while a session or trip is live, so recording survives backgrounding. Stops itself
  when there is nothing to record (car off, adapter asleep) to avoid battery drain.
- **Backend** — `logbook_entries.source` column (`manual` default / `obd_auto`) added
  via Alembic migration; the mobile logbook screen labels auto trips "auto (OBD)".
- Guardrails: auto-recording only runs when `obd_enabled` + `obd_auto_connect` are on;
  the adapter still sleeps on ignition-off (we never ping it awake); iOS is out of
  scope for the iCar Pro (see below).

## Phone path (AUT-367) — car-kit Bluetooth, no OBD adapter

Complementary to the VGate path and sharing the SAME auto start/stop recorder
(`feedCarConnection` on `ObdTripRecorder`): when the phone links to the car's
head-unit/car-kit Bluetooth (Android ACL broadcasts over a platform event
channel), a trip is armed, then starts once GPS speed is sustained above a
threshold (`lib/services/car/car_kit_trip_monitor.dart`); the link dropping or
the car going quiet closes the trip with distance from the GPS odometer diff.
Requires no Android Auto approval (it is phone-side only). Backend accepts
`source=car_auto` trips and a caller-provided `distance_km` on logbook update;
the logbook labels these "auto (car kit)". Deterministic, no AI.

## Next steps (mobile app)

1. **Adapter + protocol** — pick a generic ELM327/OBDLink adapter supporting logging and sleep-on-idle; log standard OBD-II PIDs; validate the (non-universal) odometer PID per make; plan dashboard-photo OCR / manual entry fallbacks. ✅ ELM327 SPP on Android shipped (AUT-362).
2. **Bluetooth transport** — Android: Bluetooth Classic SPP/RFCOMM (ELM327 serial profile) ✅ shipped. iOS: Bluetooth Classic is not public; use a BLE ELM327 (UART GATT) — the key platform divergence.
3. **Realtime logging to logbook** — background sampling on Android ✅ shipped (AUT-362); ignition-on starts a trip, ignition-off completes it (time, GPS, odo, distance).
4. **VIN + fault codes** — read VIN (mode 09) on first connect ✅ shipped; read DTCs (mode 03/07) ✅ shipped, save, and offer "Diagnose with AI".
5. **Account gating** — read `/obd/settings`; show lock screen when `!enabled` ✅ shipped.

## iOS note (AUT-362) — do not implement on BT Classic

- The VGate iCar Pro is **Bluetooth Classic**, which iOS apps cannot use (no public
  BT-Classic API). iOS parity requires a **BLE ELM327 adapter** (e.g. **VLinker MC+**,
  a BLE/BTClassic combo — pair it in BLE mode).
- Even with a BLE adapter, iOS **background execution limits** (no sustained
  background BLE/UART polling without a permitted background mode) prevent the same
  leave-in-the-phone auto-recording that Android gets from its foreground service.
  Expect iOS auto-trip recording to be session-limited (trip must start/end with the
  app foregrounded) or gated behind a connected-mode entitlement — full parity is not
  achievable on iOS today.

## Risks / notes

- iOS has no Bluetooth Classic — a BLE (or Wi-Fi/CAN bridge) adapter is required for iPhone.
- The odometer PID is not universal — validate per make/model; keep the photo-OCR and manual fallbacks.
- ELM327 adapters are widely cloned with varying firmware — test auto-sleep per unit.
- Prefer adapters with sleep-on-idle / auto-off to avoid battery drain.

## Definition of done

- Bluetooth auto-connect on app open when enabled.
- A single drive produces a logbook trip (start/end time, GPS, odo, distance, work flag) with no manual entry.
- VIN autofill when missing on first connect.
- Fault codes saved and one-tap into AI diagnostics.
- Works on both Android (SPP) and iPhone (BLE adapter); admin-gated per account; adapters sold white-labelled with logging + auto-off.