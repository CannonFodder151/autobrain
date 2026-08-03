# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- Live 9Router integration: OpenAI-compatible router client (`AI_ROUTER_URL`/`AI_ROUTER_MODEL`), per-module strict-JSON prompts, tolerant schemas.
- Web app delivery: Flutter web build served at `/` behind the proxy nginx.
- Cross-platform download helpers (browser download on web, share sheet on mobile).
- Comprehensive README with live URLs, web + mobile build instructions, 9Router config.
- TOTP multi-factor authentication (setup QR, enable/disable, MFA-gated login).
- Role-based access (admin/user) with admin user management and seeded bootstrap admin.
- No self-signup: account creation restricted to administrators.
- Australian rego lookup: expanded AU plate heuristics (never 404s on a valid plate), optional provider hook.
- Modern Material 3 UI overhaul (login, home dashboard, feature grid, settings, admin screens).
- SMTP email notifications (account welcome, MFA changes, password changes) via `SMTP_*` env config.
- Self-service password reset (request link → TOTP-free JWT reset token → new password) with email delivery.
- App logo asset (`frontend/assets/logo.png`) used in login + app bar.
- State-aware Australian rego lookup (NSW/VIC/QLD/WA/SA/TAS/NT/ACT) with personalised-plate word decoding (e.g. TCRWN/VIC → Toyota Crown).
- plateapi.com.au provider integration (env-configured `REGO_LOOKUP_URL`/`REGO_LOOKUP_API_KEY`, never hardcoded) with tolerant response mapping incl. year-range + description.
- Services overhaul: scheduled/completed status, upcoming vs history sections, expandable editable service cards, mark-completed checkbox, common-item checklist + unlimited free-form extra items, work steps, AI diagnostic → scheduled service with steps + parts (incl. part numbers), reports include items and exclude future services, analytics/TCO exclude scheduled until completed.

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
