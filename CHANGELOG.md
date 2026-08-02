# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
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
