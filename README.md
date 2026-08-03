# AutoBrain

AI-powered car enthusiast companion. Manage vehicles, track maintenance & fuel, run AI diagnostics, log modifications, scan receipts, manage parts inventory, estimate resale value, and get analytics — with every AI feature routed through your **9Router** instance.

![stack](https://img.shields.io/badge/stack-FastAPI%20%7C%20Flutter%20%7C%20PostgreSQL%20%7C%20Redis%20%7C%20MinIO%20%7C%20Celery-0D9488)

<div align="center" style="margin:24px 0">

[![Try AutoBrain](https://img.shields.io/badge/Try%20AutoBrain-Explore%20the%20Website-%2300B7FF?style=for-the-badge&labelColor=%23050505)](https://autobrainservice.app)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-Open%20the%20App-%23007BFF?style=for-the-badge&labelColor=%23050505)](https://demo.autobrainservice.app)
[![Self-Host](https://img.shields.io/badge/Self%20Host-Get%20Started-%231A4DFF?style=for-the-badge&labelColor=%23050505)](https://autobrainservice.app/#selfhost)

</div>

**demo@autobrainservice.app / `demo`** — read-only sample garage with 2 vehicles, services, fuel, parts & mods. AI and write features are disabled.

## Try it / get it

- **Website & hosted service** — <https://autobrainservice.app> (sales: sales@autobrainservice.app)
- **Live demo** — <https://demo.autobrainservice.app> (login: `demo@autobrainservice.app` / `demo`)
- **Live app** — <https://default.autobrainservice.app/>
- **Source** — this repository (MIT)

## Live deployment

| Service | URL |
|---------|-----|
| **Website** | https://autobrainservice.app |
| **Live demo** | https://demo.autobrainservice.app |
| **Web app** | https://default.autobrainservice.app/ |
| API (OpenAPI docs) | https://default.autobrainservice.app/api/v1 and https://default.autobrainservice.app/docs |
| AI gateway health | https://default.autobrainservice.app/ai/health |

> Everything is served from one host behind nginx: `/` → Flutter web app, `/api/*` → backend, `/ws/*` → WebSocket, `/ai/*` → AI gateway. Same-origin means no CORS config is needed.

## Features

- **Vehicle management** — multiple profiles, Australian rego lookup → VIN/make/model/year/engine, unified timeline.
- **Maintenance tracking** — service logs, AI next-service prediction, PDF/CSV export.
- **Fuel tracker** — L/100km, cost/km, efficiency & cost graphs, AI insights.
- **AI diagnostics** — symptoms + OBD codes → causes, severity, parts, cost estimate; add to next service.
- **Modification tracker** — AI performance/value impact, exportable build sheet.
- **Receipt & parts scanner** — OCR extracts parts, labour, cost, warranty; auto-adds to services + inventory.
- **Parts inventory** — quantities, usage tracking, AI reorder suggestions.
- **Resale value estimator** — value range, trend, recommendations.
- **Analytics** — spend, total cost of ownership, cost/km, 12-month forecast.
- **Security** — TOTP multi-factor authentication, role-based access (admin/user), admin-only user provisioning (no self signup).

## Architecture

```
┌────────────┐  HTTPS/WSS   ┌──────────────────────────────┐
│  Flutter   │─────────────▶│  nginx (:80)                 │
│ iOS/And/Web│◀─────────────│  / → web app, /api, /ws, /ai │
└────────────┘              └──────┬───────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
      ┌───────────────┐    ┌───────────────┐    ┌───────────────┐
      │  FastAPI      │    │  AI gateway   │    │  (static web) │
      │  + Celery     │    │  (5 modules)  │    └───────────────┘
      └──────┬────────┘    └──────┬────────┘
             │                    │ AI_ROUTER_URL
   PostgreSQL Redis MinIO        ▼
             │              ┌──────────┐
             └── Celery ────▶│  9Router │
                             └──────────┘
```

## Quick start (local development)

Requirements: Docker 24+ and Docker Compose v2. No local Python/Flutter needed.

```bash
git clone https://github.com/CannonFodder151/autobrain.git
cd autobrain
cp .env.example .env

# optional: point AI at your 9Router instance
#   edit .env → AI_ROUTER_URL=http://<router>:<port>/v1
#                AI_ROUTER_MODEL=General-Use
docker compose up -d --build
```

Verify:

```bash
curl http://localhost:8000/health        # backend
curl http://localhost:8001/health        # AI gateway (shows router_enabled)
open http://localhost:8000/docs          # OpenAPI
```

## AI / 9Router integration

All five AI modules (diagnostics, service prediction, OCR, resale value, mod impact) read `AI_ROUTER_URL` **at runtime** and call it in OpenAI chat-completions format:

```
POST {AI_ROUTER_URL}/chat/completions
Authorization: Bearer {AI_ROUTER_API_KEY}
{"model": "General-Use", "messages": [...], "stream": false}
```

| Env var | Purpose | Default |
|---------|---------|---------|
| `AI_ROUTER_URL` | 9Router base URL (usually ends in `/v1`) | `http://your-9router-instance:port/v1` |
| `AI_ROUTER_API_KEY` | Bearer key for the router | *(empty)* |
| `AI_ROUTER_MODEL` | Model id served by the router (see `GET /v1/models`) | `General-Use` |
| `AI_ROUTER_TIMEOUT_SECONDS` | Per-request timeout | `120` |

**Failure behaviour:** if the router is unreachable, misconfigured or times out, each module falls back to a deterministic rule-based engine — the platform keeps working offline. Every response includes a `model` field (`"9router"`/model-id or `"rule-based-fallback"`).

To confirm routing is live: `curl http://<host>/ai/health` → `"router_enabled": true`.

## Web app

The Flutter app builds for iOS, Android **and** web. The web build is produced by:

```bash
docker build -f docker/frontend/Dockerfile \
  --build-arg API_BASE_URL=http://<host>/api/v1 \
  --build-arg WS_BASE_URL=ws://<host>/ws \
  -t autobrain-frontend:web .
```

Extract the built site and serve it behind the proxy nginx:

```bash
docker create --name ab-web autobrain-frontend:web
docker cp ab-web:/usr/share/nginx/html ./web-dist
docker rm ab-web
docker compose -f docker-compose.prod.yml up -d nginx   # mounts ./web-dist
```

## Mobile app (iOS/Android)

```bash
cd frontend
flutter pub get

# regenerate platform boilerplate once (org/app id)
flutter create . --platforms=android,ios --org com.autobrain

# point at your backend, then build
flutter build apk --release \
  --dart-define=API_BASE_URL=https://default.autobrainservice.app/api/v1 \
  --dart-define=WS_BASE_URL=wss://default.autobrainservice.app/ws

flutter build ios --release   # requires macOS + Xcode
```

`lib/` layout: `core/` (API client, auth, offline SQLite cache, models), `screens/` (all 12 feature screens), `widgets/`.

## Security & access

- **No self signup.** Accounts are provisioned by an administrator only (`/api/v1/admin/users`, or the in-app "User administration" screen). Anonymous registration returns `401`.
- **Roles.** `admin` (manages users + all data) and `user`. Admin endpoints return `403` for non-admins.
- **MFA (TOTP).** Any user can enable two-factor auth from *Settings & security* (scan the QR with Google Authenticator / Authy / 1Password). Login then requires a 6-digit code; the backend never issues a full session without it.
- **Bootstrap admin.** On first boot the app creates the admin account from `ADMIN_EMAIL` / `ADMIN_INITIAL_PASSWORD` in `.env` (see `.env.example`). Rotate the password after first login.

## Australian rego lookup

Rego lookup accepts any valid Australian plate + state (NSW/VIC/QLD/WA/SA/TAS/NT/ACT) and auto-fills VIN, make, model, year and engine. Two sources:

1. **plateapi.com.au (real registry data)** — set `REGO_LOOKUP_URL=https://api.plateapi.com.au/api/v1/lookup` and `REGO_LOOKUP_API_KEY` in `.env` (key is never hardcoded or committed). Requests use `?plate=…&state=…` with `X-API-Key`. The free tier is **20 lookups/month**; lookups run only on demand (when you tap Lookup). The free tier returns make/model/engine + production-year range (no VIN).
2. **Offline heuristic** — when no provider is configured, or the provider is unreachable, the app returns a best-effort guess (`source: heuristic`) so the feature never 404s on a valid plate.

## Deployment (production)

The production stack runs from **pre-built Docker Hub images** — no build step on the host.

### 1. Publish images

```bash
DOCKERHUB_USERNAME=cannonfodder151 ./scripts/publish-images.sh   # builds + pushes all 4 images
```

Images: `cannonfodder151/autobrain-{backend,worker,ai,frontend}:latest` and `cannonfodder151/autobrain-frontend-demo:latest`.

### 2. Deploy the stack (docker compose on a Linux host)

```bash
git clone https://github.com/CannonFodder151/autobrain.git
cd autobrain
cp .env.example .env                       # fill SECRET_KEY, ADMIN_*, SMTP_*, AI_ROUTER_URL
DOCKERHUB_USERNAME=cannonfodder151 IMAGE_TAG=latest \
  docker compose -f docker-compose.prod.yml up -d
```

Or point the same `docker-compose.prod.yml` at a **Portainer** environment and let it pull the published images. First boot applies migrations automatically (`python -m app.db.bootstrap`; Alembic, falling back to `create_all`) and seeds the admin account from `ADMIN_EMAIL`/`ADMIN_INITIAL_PASSWORD`.

### 3. Optional: run the read-only demo

Set `DEMO_MODE=true` (plus `DEMO_EMAIL`/`DEMO_PASSWORD`) to seed a read-only demo account with sample data. The demo role is enforced server-side: every write endpoint returns `403` and every AI module is disabled.

```bash
DEMO_MODE=true DEMO_EMAIL=demo@example.com DEMO_PASSWORD=demo \
  docker compose -f docker-compose.prod.yml up -d backend
```

> Demo deployment in production: `cannonfodder151/autobrain-frontend-demo:latest` is a frontend build pointed at the demo API URL, exposed on port 8089 (see the AutoBrain deployment guide for the full stack file).

## Manual / bare-metal deployment

```bash
sudo ./scripts/setup-server.sh <user>   # installs docker + compose
./scripts/deploy.sh <user>@<host>        # syncs repo, builds, starts prod stack
```

`docker-compose.prod.yml` runs: postgres, redis, minio, backend, worker, beat, ai, nginx (web + reverse proxy).

Kubernetes manifests: `infra/k8s/`. systemd units: `infra/systemd/`.

## Tests

```bash
docker compose exec backend pytest     # backend (auth, health, unauth)
docker compose exec ai pytest          # AI fallback engines + router-disabled path
cd frontend && flutter test            # Dart model tests
```

## Documentation

Full docs are maintained in the Outline wiki (AutoBrain collection) and mirrored in [`docs/`](docs/README.md): system overview, module breakdown, API spec, database schema, AI model descriptions, 9Router integration, deployment guide, developer onboarding, versioning, security, backup strategy, monitoring, infrastructure diagrams, container architecture.

## Repository layout

```
/backend    FastAPI + SQLAlchemy + Celery + MinIO
/ai         AI inference gateway (5 modules) + rule-based fallbacks
/frontend   Flutter app (iOS / Android / web)
/infra      Kubernetes manifests, systemd units
/docker     Build contexts: backend, ai, worker, frontend
/scripts    deploy, server setup, backup
/docs       Markdown mirrors of the wiki
/tests      backend + ai tests
```

## License

MIT — see [LICENSE](LICENSE).
