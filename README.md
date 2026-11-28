# AutoBrain

AI-powered car enthusiast companion. Manage vehicles, track maintenance & fuel, run AI diagnostics, log modifications, scan receipts, manage parts inventory, estimate resale value, and get analytics — with every AI feature routed through your **9Router** instance.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.326-green)](CHANGELOG.md)

- **Website / hosted service** — https://autobrainservice.app
- **Live demo** — https://demo.autobrainservice.app (login: `demo@autobrainservice.app`; password distributed via the Paperclip secret `demo/demo-account-password`, set on the demo stack as `DEMO_PASSWORD`)
- **Marketing site** — https://autobrainservice.app (repo: `autobrainservice-website`)
- **AU rego lookup API** — self-hosted Plate-API-Scraper (`rego-lookup-api` repo)
- **Mobile app** — [`CannonFodder151/autobrain-mobile`](https://github.com/CannonFodder151/autobrain-mobile) (private)

## Quick start (Docker)

Requires Docker 24+ and Docker Compose v2. No other toolchain needed.

```bash
git clone https://github.com/CannonFodder151/autobrain.git
cd autobrain
cp .env.example .env      # then edit .env — see Environment variables below
docker compose -f docker-compose.prod.yml up -d
```

First boot applies DB migrations and creates the admin account automatically.

### Development (from source)

```bash
cp .env.example .env
# Edit .env with your values (at minimum SECRET_KEY, AI_ROUTER_URL, AI_ROUTER_API_KEY, ADMIN_EMAIL, ADMIN_INITIAL_PASSWORD)
docker compose up -d --build
```

Services:
- API docs: http://localhost:8000/docs (Swagger UI)
- AI gateway docs: http://localhost:8001/docs
- MinIO console: http://localhost:9001
- Frontend: http://localhost:8080

### Production (prebuilt images)

```bash
cp .env.example .env
# Fill in all required values from .env.example
docker compose -f docker-compose.prod.yml up -d
```

Prod runs behind nginx on port 80:
- `/api/*` → backend
- `/ws/*`  → backend WebSocket
- `/ai/*`  → AI gateway
- `/`      → Flutter web build

## Environment variables

Copy `.env.example` to `.env` and set at minimum:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | JWT signing key — generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ADMIN_EMAIL` / `ADMIN_INITIAL_PASSWORD` | Bootstrap admin account (created on first boot) |
| `AI_ROUTER_URL` / `AI_ROUTER_API_KEY` / `AI_ROUTER_MODEL` | Point AI at any OpenAI-compatible router (see `.env.example`) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM_EMAIL` | Email notifications + password reset |
| `APP_BASE_URL` | Public URL used to build password-reset links |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | PostgreSQL credentials |
| `REDIS_PASSWORD` | Redis password (required) |
| `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | MinIO/S3 credentials |

Optional highlights:
- `DEMO_MODE=true` — seeds a read-only demo account with sample data.
- `MFA_ENFORCED=true` — requires two-factor auth for all non-demo accounts.
- `REGO_LOOKUP_URL` / `REGO_LOOKUP_API_KEY` — enable Australian rego lookups via self-hosted Plate-API-Scraper (POST `/lookup`, `X-API-Key` header). Offline heuristic covers failures.
- `SELF_SIGNUP_ENABLED=true` — enables self-service Free-tier signup; the app hides the "Create a free account" button when `false` (default).
- `LICENSE_ENABLED=true` — turns on the licence/upgrade page (hosted instance; off for self-hosted/demo).
- `STRIPE_SECRET_KEY` + related — enables Stripe billing (hosted subscriptions).
- `BACKUP_ENABLED=true` / `BACKUP_RETENTION_DAYS=14` — daily DB JSON snapshots to MinIO.
- `ADMIN_API_KEY` — machine-to-machine user management via `/api/v1/admin-api/*`.
- `DEMO_MODE`, `DEMO_EMAIL`, `DEMO_PASSWORD` — demo account credentials.
- `CARTO_API_KEY` — required for frontend map tiles (AUT-4690).
- `FUEL_NSW_API_KEY` / `FUEL_VIC_API_KEY` / `FUEL_QLD_API_KEY` — fuel price map data sources (premium).

See `.env.example` for the full list with comments.

## Verify it's running

```bash
curl http://localhost:8000/health        # backend
curl http://localhost:8001/health        # AI gateway
```

## API Documentation

- **OpenAPI/Swagger**: http://localhost:8000/docs (backend), http://localhost:8001/docs (AI gateway)
- **OpenAPI JSON**: http://localhost:8000/openapi.json
- **ReDoc**: http://localhost:8000/redoc

See [`openapi.json`](openapi.json) in the repo root for the full specification.

## Services

`docker-compose.prod.yml` runs: **postgres, redis, minio, backend (API + AI gateway + Celery worker+beat in-container), frontend** — 5 containers. The frontend nginx container serves the Flutter web app at `/` and proxies `/api/*`, `/ws/*`, `/ai/*` to backend/AI — same-origin, no CORS needed. The AI gateway runs as a subprocess on `:8001` inside the backend container.

`docker-compose.hosted.yml` runs the same stack plus Stripe billing and self-service signup, with prebuilt images. Hosted uses 8 containers: postgres, redis, minio, backend, ai, frontend, hub, 9router — with a separate `ai` container (AI gateway + market-data) and dedicated `9router` instance.

| Service | Image | Notes |
|---------|-------|-------|
| postgres | `pgvector/pgvector:pg17` (pinned by digest) | healthcheck `pg_isready`; volume `postgres-data` |
| redis | `redis:7-alpine` | healthcheck `redis-cli ping`; volume `redis-data` |
| minio | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | pinned (AUT-322); healthcheck `mc ready local`; volume `minio-data` |
| backend | `autobrain-backend:<tag>` | API on `:8000` (internal); **Celery worker+beat merged in** (AUT-3153); `/health` |
| ai | `autobrain-ai:<tag>` | AI gateway on `:8001` (internal); `/health` |
| frontend | `autobrain-frontend:<tag>` | nginx serves Flutter web + proxies `/api/*`, `/ws/*`, `/ai/*` |
| hub | `ghcr.io/cannonfodder151/autobrain-federation-hub:<tag>` | federation hub (Community Garage); built from private repo |
| 9router | `ghcr.io/cannonfodder151/9router:<tag>` | AI router (OpenAI-compatible) |

## Documentation

Full docs are maintained in the Outline wiki (AutoBrain collection) and mirrored in [`docs/`](docs/index.md).

### Key documentation files

| File | Description |
|------|-------------|
| [Deployment Guide](docs/Deployment-and-Infrastructure/deployment-guide.md) | Complete deployment procedures for all tiers |
| [Deploy Runbook](docs/runbooks/deploy.md) | Step-by-step deployment runbook |
| [Backup & Restore Runbook](docs/runbooks/backup-restore.md) | Admin backup, off-site backup, disaster recovery |
| [Database Migration Runbook](docs/runbooks/database-migration.md) | Alembic migration procedures and troubleshooting |
| [Secret Rotation Runbook](docs/runbooks/secret-rotation.md) | Rotate secrets across environments |
| [Health Check Runbook](docs/runbooks/health-check.md) | Service health verification and troubleshooting |
| [Incident Response Runbook](docs/runbooks/incident-response.md) | Incident classification, escalation, and resolution |
| [Shop Deployment](docs/shop-deployment.md) | AutoBrain Shop deployment on Oracle VM |
| [Developer Onboarding](docs/Engineering/developer-onboarding.md) | Getting started for developers |
| [Architecture](docs/Engineering/architecture.md) | System architecture overview |
| [Database Schema](docs/Engineering/database-schema.md) | Database schema documentation |
| [Security](docs/Security/security.md) | Security policies and procedures |
| [OBD2 Dongle Build](docs/Engineering/obd2-dongle/README.md) | Hardware build documentation |

## Repository layout

```
 backend/    FastAPI + SQLAlchemy + Celery + MinIO
 ai/         AI inference gateway (12 modules) + rule-based fallbacks
 frontend/   Flutter web frontend
 infra/      Kubernetes manifests, systemd units, nginx config
 docker/     Build contexts: backend (unified API+AI+worker), ai, frontend
 scripts/    deploy, backup, setup-server, publish-images, bump-version
 docs/       Markdown mirrors of the Outline wiki
 firmware/   OBD2 dongle firmware (ESP32 + CAN + GPS)
```

## Mobile app split

The **mobile app** (iOS/Android) lives in its own private repo:
[`CannonFodder151/autobrain-mobile`](https://github.com/CannonFodder151/autobrain-mobile).
This repo (`frontend/`) keeps the **Flutter web** build only. The two repos
share the same Flutter codebase lineage and the same release version:

- `autobrain` — web frontend (built by the frontend Docker image)
- `autobrain-mobile` — iOS / Android app (built with Flutter tooling)

`scripts/bump-version.sh --mobile` bumps `autobrain-mobile`'s `pubspec.yaml`
in the same release, so store versions always match the server release. On
login the app compares its installed version with the server's
`GET /api/v1/auth/config` → `app_version` and prompts the user to update
when it is behind.

## AI modules

All AI features route through 9Router (OpenAI-compatible). If the router is unreachable, deterministic rule-based fallbacks activate automatically. The `model` field in responses tells you which path produced the result (`"9router"` or `"rule-based-fallback"`).

| Module | Endpoint | Description |
|--------|----------|-------------|
| Diagnostics | `/v1/diagnostics` | Symptoms + OBD codes → causes, severity, parts, cost |
| Service prediction | `/v1/service-prediction` | Next service interval + due km/date |
| OCR | `/v1/ocr` | Receipt scan → vendor, items, totals, warranty |
| Fuel receipt | `/v1/fuel-ocr` | Fuel receipt → litres, price/L, total |
| Odometer | `/v1/odometer` | Dashboard photo → odometer reading |
| Resale | `/v1/resale` | Vehicle attributes → value estimate + trend |
| Mod impact | `/v1/mod-impact` | Modification → performance/value/reliability impact |
| Advisor | `/v1/advisor` | Maintenance planning + cost forecasting |
| Car check | `/v1/car-check` | Vehicle inspection checklist generation |
| Condition | `/v1/condition` | Vehicle condition scoring from photos |
| Parts guide | `/v1/parts-guide` | Parts compatibility + sourcing |
| Social image | `/v1/social-image` | Community post image generation |
| Health score | `/vehicles/{id}/health-score` | Vehicle health score (deterministic-first + 9Router) |

## Key features

- **Vehicle management** — profiles, rego lookup (car/motorcycle), unified timeline
- **Maintenance tracking** — service logs, AI prediction, PDF/CSV/ZIP export
- **Fuel tracker** — L/100km, cost/km, efficiency graphs, receipt OCR
- **AI diagnostics** — symptoms → causes, severity, parts, cost; link to services
- **Modification tracker** — AI impact summaries, build sheet export
- **Receipt & parts scanner** — OCR extraction, parts inventory, reorder suggestions
- **Resale value estimator** — value + trend + recommendations
- **ATO logbook** — work/private trip logging, CSV export per financial year
- **OBD-II** — fault codes, VIN autofill, live diagnostics (in progress)
- **Analytics** — fuel/service/mod spend, total cost of ownership, cost/km, forecast
- **MFA** — TOTP (RFC 6238) with QR setup, login flow
- **Multi-tier** — Free, Enthusiast, Garage plans via Stripe (hosted)
- **Profile export/import** — download/import your whole account as JSON
- **Admin backup & restore** — full JSON snapshot, wipe-and-restore, scheduled backups
- **Community Garage** — social features, issues blog, federation hub
- **Petrol price map (Servo Spy)** — NSW/QLD/VIC/WA/SA fuel prices with map view (premium)
- **OBD2 dongle** — phone-free trip logging hardware (ESP32 + CAN + GPS)

## Deployment

### Promotion order (MANDATORY)

1. **Demo** — `demo.autobrainservice.app` (public, low-risk, demo account)
2. **Default** — `default.autobrainservice.app` (internal dev/default instance)
3. **Hosted** — `hosted.autobrainservice.app` (Oracle Cloud, production)

> **Never skip or reorder tiers.** A change never goes to Hosted without first passing Demo and Default.

See [Deployment Guide](docs/Deployment-and-Infrastructure/deployment-guide.md) and [Deploy Runbook](docs/runbooks/deploy.md) for complete procedures.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/developer-onboarding.md](docs/developer-onboarding.md).

## License

MIT — see [LICENSE](LICENSE).