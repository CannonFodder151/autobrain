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

## Next steps (mobile app)

1. **Adapter + protocol** — pick a generic ELM327/OBDLink adapter supporting logging and sleep-on-idle; log standard OBD-II PIDs; validate the (non-universal) odometer PID per make; plan dashboard-photo OCR / manual entry fallbacks.
2. **Bluetooth transport** — Android: Bluetooth Classic SPP/RFCOMM (ELM327 serial profile). iOS: Bluetooth Classic is not public; use a BLE ELM327 (UART GATT) — the key platform divergence.
3. **Realtime logging to logbook** — background sampling on Android; ignition-on starts a trip, ignition-off completes it (time, GPS, odo, distance).
4. **VIN + fault codes** — read VIN (mode 09) on first connect; read DTCs (mode 03/07), save, and offer "Diagnose with AI".
5. **Account gating** — read `/obd/settings`; show lock screen when `!enabled`.

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