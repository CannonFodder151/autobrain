# AutoBrain

AI-powered car enthusiast companion. Manage vehicles, track maintenance & fuel, run AI diagnostics, log modifications, scan receipts, manage parts inventory, estimate resale value, and get analytics — with every AI feature routed through your **9Router** instance.

- **Website / hosted service** — https://autobrainservice.app (sales: sales@autobrainservice.app)
- **Live demo** — https://demo.autobrainservice.app (login: `demo@autobrainservice.app` / `demo`)
- **License** — MIT

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

Optional: `DEMO_MODE=true` seeds a read-only demo account with sample data. `MFA_ENFORCED=true` requires two-factor auth for all non-demo accounts. `REGO_LOOKUP_URL` / `REGO_LOOKUP_API_KEY` enable Australian rego lookups. `SELF_SIGNUP_ENABLED=true` enables self-service Free-tier signup (a setup email completes the account); when `false` (default) the signup endpoint is disabled **and the app hides the "Create a free account" button** — the app learns this from the public `GET /auth/config` endpoint.

See `.env.example` for the full list with comments.

## Verify it's running

```bash
curl http://localhost:8000/health        # backend
curl http://localhost:8001/health        # AI gateway
```

## Services

`docker-compose.prod.yml` runs: **postgres, redis, minio, backend, worker, beat, ai, nginx**. Nginx serves the web app at `/` and proxies `/api/*`, `/ws/*`, `/ai/*` to the backend/AI gateway — same-origin, so no CORS config is needed.

## Documentation

Full docs are maintained in the Outline wiki (AutoBrain collection) and mirrored in [`docs/`](docs/README.md).

## Repository layout

```
/backend    FastAPI + SQLAlchemy + Celery + MinIO
/ai         AI inference gateway (5 modules) + rule-based fallbacks
/frontend   Web frontend (Flutter web)
/infra      Kubernetes manifests, systemd units
/docker     Build contexts: backend, ai, worker, frontend
/scripts    server setup, backup
/docs       Markdown mirrors of the wiki
```
