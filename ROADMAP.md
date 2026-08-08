# Roadmap

## Shipped (v0.3.4)

- Vehicle management with rego lookup, colour, body type, vehicle type (car/motorcycle)
- Maintenance tracking with AI service prediction, PDF/CSV export
- Fuel tracker with L/100km, cost/km, efficiency graphs, AI insights, per-FY export
- AI diagnostics (symptoms + OBD codes → causes, severity, parts, cost)
- Receipt & parts OCR scanner
- Parts inventory with quantities, usage, AI reorder suggestions
- Resale value estimator with trend + recommendations
- Modifications tracker with AI impact summaries, build sheet export
- Analytics dashboard (fuel/service/mod spend, TCO, cost/km, forecast)
- ATO logbook with GPS, per-FY CSV export, dashboard-odometer OCR
- Multi-factor authentication (TOTP)
- Profile export/import, admin backup & restore
- Self-service Free signup + Stripe billing (hosted)
- OBD-II fault-code library with AI diagnostics integration
- Flutter web + Android (Google Play)
- Docker Compose (dev, prod, hosted), Kubernetes manifests

## In progress

- Phase 1 code review & improvement initiative
- Mobile app split into `autobrain-mobile` repo
- Reduce container count: consolidate beat into worker, merge AI gateway into backend image
- Vectorise data for efficient storage
- Make AI functions less AI-dependent (deterministic-first, AI fallback)

## Planned (short term)

- Live OBD-II Bluetooth logging (Android RFCOMM, iOS BLE adapter)
- Service/maintenance reminders (push notifications)
- Discord webhook notifications
- Container health dashboard (Portainer integration)
- Offline-mode sync (mobile → server on reconnect)
- Hosted stack move to Oracle Cloud (Phase 3)

## Deferred / future

- Community garage — share builds, leaderboards
- Multi-user garage (shared vehicles across accounts)
- Insurance integration (quote estimates from vehicle data)
- Marketplace — list parts/mods for sale
- iOS App Store launch
- OpenTelemetry tracing
