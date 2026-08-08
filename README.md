# AutoBrain

AI-powered car enthusiast companion. Manage vehicles, track maintenance & fuel, run AI diagnostics, log modifications, scan receipts, manage parts inventory, estimate resale value, and get analytics — with every AI feature routed through your **9Router** instance.

[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.3.4-green)](CHANGELOG.md)

- **Website / hosted service** — https://autobrainservice.app
- **Live demo** — https://demo.autobrainservice.app (login: `demo@autobrainservice.app` / `demo`)
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

## Environment variables

Copy `.env.example` to `.env` and set at minimum:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | JWT signing key — use a long random string |
| `ADMIN_EMAIL` / `ADMIN_INITIAL_PASSWORD` | Bootstrap admin account (created on first boot) |
| `AI_ROUTER_URL` / `AI_ROUTER_API_KEY` / `AI_ROUTER_MODEL` | Point AI at any OpenAI-compatible router (see `.env.example`) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_FROM_EMAIL` | Email notifications + password reset (uses the system SMTP) |
| `APP_BASE_URL` | Public URL used to build password-reset links |

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

See `.env.example` for the full list with comments.

## Verify it's running

```bash
curl http://localhost:8000/health        # backend
curl http://localhost:8001/health        # AI gateway
```

## Services

`docker-compose.prod.yml` runs: **postgres, redis, minio, backend, worker, beat, ai, nginx**. Nginx serves the web app at `/` and proxies `/api/*`, `/ws/*`, `/ai/*` to the backend/AI gateway — same-origin, so no CORS config is needed.

`docker-compose.hosted.yml` runs the same stack plus Stripe billing and self-service signup, with prebuilt Docker Hub images (`cannonfodder151/autobrain-*:hosted`).

## Documentation

Full docs are maintained in the Outline wiki (AutoBrain collection) and mirrored in [`docs/`](docs/README.md).

## Repository layout

```
/backend    FastAPI + SQLAlchemy + Celery + MinIO
/ai         AI inference gateway (7 modules) + rule-based fallbacks
/frontend   Flutter web frontend
/infra      Kubernetes manifests, systemd units, nginx config
/docker     Build contexts: backend, ai, worker, frontend
/scripts    deploy, backup, setup-server, publish-images, bump-version
/docs       Markdown mirrors of the wiki
```

## Mobile app split

The **mobile app** (iOS/Android) lives in its own private repo:
[`CannonFodder151/autobrain-mobile`](https://github.com/CannonFodder151/autobrain-mobile).
This repo (`frontend/`) keeps the **Flutter web** build only. The two repos
share the same Flutter codebase lineage but are versioned independently:

- `autobrain` — web frontend (built by the frontend Docker image)
- `autobrain-mobile` — iOS / Android app (built with Flutter tooling)

`scripts/bump-version.sh` accepts `--mobile` to bump `autobrain-mobile`'s
`pubspec.yaml` alongside a web release.

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/developer-onboarding.md](docs/developer-onboarding.md).

## License

MIT — see [LICENSE](LICENSE).
