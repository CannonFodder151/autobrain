# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.2.4] - 2026-08-05

### Added
- `SELF_SIGNUP_ENABLED` now also drives the UI: the app fetches public `GET /auth/config` (`signup_enabled`) and hides the "Create a free account" button when disabled. Signup stays on by default for the hosted instance and is disabled on demo/default (admin-provisioned).

## [0.2.3] - 2026-08-05

### Fixed
- Receipt uploads: the app now sends a real file MIME type (it previously always sent `application/octet-stream`, which the fuel-receipt endpoint rejected with "unsupported file type").
- Backend now sniffs file type from magic bytes (PDF/JPEG/PNG/WEBP) before trusting the upload header, so photos from phone/camera pickers work for fuel receipts, receipts scanner and odometer OCR. HEIC/TIFF now accepted too.

## [0.2.2] - 2026-08-05

### Fixed
- Web autofill: removed the global Enter-key interceptor that could swallow browser password-manager fills (Enter still submits via the fields themselves).
- MFA code fields now carry `one-time-code` autofill hints so browsers offer the OTP/password suggestion (login, MFA setup, and Settings & security).

## [0.2.1] - 2026-08-05

### Added
- Vehicle body type field (add/edit form, rego-lookup auto-fill, shown on vehicle cards and home screen).

## [0.2.0] - 2026-08-05

### Added
- Vehicle colour field (add/edit form, rego-lookup auto-fill, shown on vehicle cards and home screen).
- Self-service Free-tier signup (hosted): display name + email only; a 7-day setup email completes the account (choose password + MFA, enforced on the hosted instance).
- Stripe self-service billing: Checkout, Customer Portal, cancel-at-end-of-period, webhook promote/demote between free and paid plans.
- OBD2 hardware companion listed as a **Coming soon** product on the marketing site (not part of subscription plans).
- ATO logbook: per-trip logging for non-club-reg vehicles (start/end time, GPS, odometer, work/private, reason), edit/complete trips, per-financial-year CSV export, and dashboard-photo odometer OCR (AI). Completing a trip updates the vehicle odometer.
- Club registration selector on vehicles — club-registered vehicles disable the logbook feature.
- Fuel: edit/delete fill-ups, fuel-receipt photo upload (AI parse of litres/price-per-litre, or plain upload without AI), and per-financial-year CSV export for tax purposes. Fuel always updates the odometer unless a newer logbook trip governs.
- Free account tier (`free_account` per user): disables AI features and rego lookup (403 server-side); file exports are available on all plans.
- Server version in admin settings with GitHub latest-release check (up to date / update available).
- Diagnostics: resolve + delete once fixed; a diagnostic auto-flips to resolved (green tick) when its linked scheduled service is completed.
- Profile export/import: download your whole account as JSON and import it on any server.
- Admin backup & restore: full JSON database snapshot download, wipe-and-restore endpoint, and a scheduled daily backup (Celery beat → MinIO) with retention.
- Admin API key (`ADMIN_API_KEY` + `X-Admin-API-Key`): create users, set permissions (role, vehicle quota, free/paid account, OBD access), list, disable and delete users machine-to-machine.
- OBD-II seam: fault-code library with save/pull-to-AI-diagnostics, VIN auto-fill, admin-gated per-account access, Bluetooth auto-connect setting, and a "work in progress" UI for the live adapter features.
- AI gateway: new `fuel-ocr` and `odometer` modules; all modules run at temperature 0 with validated/clamped numeric output (resale low ≤ est ≤ high) for stable estimates.
- Azure/cloud web build fix: hermetic `pub get` (pubspec.lock copied) and removed the vestigial `build_runner` step.
- Live 9Router integration: OpenAI-compatible router client (`AI_ROUTER_URL`/`AI_ROUTER_MODEL`), per-module strict-JSON prompts, tolerant schemas.
- Web app delivery: Flutter web build served at `/` behind the proxy nginx.
- TOTP multi-factor authentication (setup QR, enable/disable, MFA-gated login) and self-service password reset.
- Role-based access (admin/user) with admin user management and seeded bootstrap admin.
- Australian rego lookup (state-aware, personalised-plate word decoding, optional plateapi.com.au provider).
- Services overhaul: scheduled/completed status, editable service cards with items + work steps, AI prediction, PDF/CSV export.
- Receipt & parts OCR, parts inventory with AI reorder suggestions, resale value estimator, analytics.

### Fixed
- Login: email field is focused and its text selected on page load (fixes the web-autofill landing issue).
- Login/MFA: the 6-digit verification code field is auto-focused when the MFA step appears.
- Login/MFA: pressing Enter on the keyboard now submits the form instead of doing nothing.
- Login: completing MFA setup no longer leaves the button spinning — the busy state is cleared and the app returns to the home screen.

### Changed
- Free accounts can export files; only AI features and rego lookup remain paid.
- MFA is no longer a paid-plan feature — available on all tiers.
- Self-service signup collects display name + email only; a setup email completes the account (password + MFA).

### Removed
- GitHub Actions CI/CD workflows.
- Initial AutoBrain scaffold.
- Vehicle management: multiple profiles, rego lookup, timeline events.
- Maintenance tracking with AI service prediction and PDF/CSV export.
- Fuel tracker with L/100km, cost/km, efficiency and cost graphs.
- AI diagnostics (symptoms → causes, severity, parts, cost).
- Modification tracker with AI impact summaries and build sheet export.
- Receipt & parts OCR extraction with auto-add to maintenance/parts.
- Parts inventory with quantities, usage and AI reorder suggestions.
- Resale value estimator with trend graph and recommendations.
- Analytics: fuel/service/mod spend, total cost of ownership, forecasts.
- AI inference layer (5 modules) routed through `AI_ROUTER_URL` (9Router).
- FastAPI backend with REST + WebSocket, PostgreSQL, Redis, MinIO, Celery.
- Flutter frontend (offline-first) for iOS and Android.
- Docker Compose (dev + prod), Dockerfiles, Kubernetes manifests, systemd.
- GitHub Actions CI/CD workflows.
- Full documentation set maintained via Outline MCP.
