# Deployment Guide

## Deployment order (promotion policy) — MANDATORY

When a new update is pushed out, roll it out in this exact order. Do not skip or
reorder a tier:

1. **Demo** — `demo.autobrainservice.app` (public, low-risk, demo account).
2. **Default** — `default.autobrainservice.app` (internal dev/default instance).
3. **Hosted** — `hosted.autobrainservice.app` (Oracle Cloud, prebuilt images).

Only promote to the next tier once the current one is verified healthy (startup,
health checks, key flows). A change never goes to Hosted without first passing
Demo and Default. A release is **NOT complete** until Hosted is verified last.
Source of truth: board directive AUT-107.

### Release checklist

Every release runs the gates below, in order. No gate may be skipped; a failed
gate blocks the release at that tier.

- [ ] 0. **Code gate** — every feature/PR for this release is **merged to `main`
      first**. Do NOT deploy, promote, or announce a feature whose PR is still
      open or unmerged.
- [ ] 1. **Demo** — deploy to `demo.autobrainservice.app`; verify startup +
      `/health` + key flows.
- [ ] 2. **Default** — deploy to `default.autobrainservice.app`; verify startup +
      `/health` + key flows.
- [ ] 3. **Hosted** — deploy to `hosted.autobrainservice.app` (Oracle Cloud VM,
      Portainer); verify startup + `/health` + key flows. **Only when this
      passes is the release complete.**
- [ ] **Verify the feature is actually present** on each tier — exercise the
      flow (open the new screen, hit the new endpoint), not just the version
      banner.
- [ ] **Post-deploy prune** — run `scripts/prune-images.sh` to drop dangling
      build-layer images on EP2 (Portainer-Host) + EP5 (AutoBrain-Hosted).
      Deploys are the main source of dangling images (AUT-350); prune every
      release so ~30-70GB does not accumulate between weekly prunes.
- [ ] Note promotion order + verification result in the issue / `#updates`
      channel.

## Environment tiers

| Tier | URL | Host | Images |
|------|-----|------|--------|
| Demo | `demo.autobrainservice.app` | Portainer-Host | `cannonfodder151/autobrain-*:latest`, frontend `:demo` |
| Default | `default.autobrainservice.app` | Portainer-Host | `cannonfodder151/autobrain-*:latest`, frontend `:default` |
| Hosted | `hosted.autobrainservice.app` | Oracle Cloud VM | `cannonfodder151/autobrain-*:hosted`, worker `:hosted` |

All three tiers run as standalone Portainer stacks with prebuilt images pulled
from Docker Hub / GHCR. Hosted is published behind Nginx Proxy Manager on the
Oracle VM; the stack frontend nginx exposes `:8086`.

## Stack services

| Service | Image | Notes |
|---------|-------|-------|
| postgres | `postgres:16-alpine` | healthcheck `pg_isready`; volume `postgres-data` |
| redis | `redis:7-alpine` | healthcheck `redis-cli ping`; volume `redis-data` |
| minio | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | pinned (AUT-322); healthcheck `mc ready local`; volume `minio-data` |
| minio-init | `minio/mc:RELEASE.2025-08-13T08-35-41Z` | one-shot bucket create; forces `anonymous set none` (bucket stays private, AUT-321) |
| backend | `autobrain-backend:<tag>` | API on `:8000` (internal); `/health` |
| worker / beat | `autobrain-worker:<tag>` | Celery worker + beat, separate containers |
| ai | `autobrain-ai:<tag>` | AI gateway on `:8001` (internal); `/health` |
| frontend | `autobrain-frontend:<tag>` | nginx serves Flutter web + proxies `/api/*`, `/ws/*`, `/ai/*` |

Only the frontend publishes a port; all internal services stay on the Compose
network.

## Prerequisites

- Linux host with Docker 24+ and Docker Compose v2.
- 4 vCPU / 8 GB RAM minimum for the full stack.
- `.env` populated from `.env.example`.

## One-time server setup

```bash
sudo ./scripts/setup-server.sh <user>
```

## Deploy (dev, from source)

```bash
cp .env.example .env
docker compose up -d --build
```

Services:
- API docs: http://localhost:8000/docs
- AI gateway: http://localhost:8001/docs
- MinIO console: http://localhost:9001

## Deploy (hosted)

```bash
./scripts/publish-images.sh hosted
# Then update the Portainer stack (AutoBrain-Hosted) to pull new images.
```

## Deploy (production, from source)

```bash
cp .env.example .env   # fill real values, especially SECRET_KEY + AI_ROUTER_URL
docker compose -f docker-compose.prod.yml up -d --build
```

Prod runs behind nginx on port 80:
- `/api/*` → backend
- `/ws/*`  → backend WebSocket
- `/ai/*`  → AI gateway
- `/`      → Flutter web build

### Web app (serve the Flutter build)

```bash
docker build -f docker/frontend/Dockerfile \
  --build-arg API_BASE_URL=http://<host>/api/v1 \
  --build-arg WS_BASE_URL=ws://<host>/ws \
  -t autobrain-frontend:web .
docker create --name ab-web autobrain-frontend:web
docker cp ab-web:/usr/share/nginx/html ./web-dist
docker rm ab-web
docker compose -f docker-compose.prod.yml up -d nginx   # mounts ./web-dist
```

## Over SSH

```bash
./scripts/deploy.sh <user>@<host>
```

## Migrations

First boot runs `python -m app.db.bootstrap` (Alembic, falling back to
`create_all`). Afterwards use Alembic:

```bash
docker compose exec backend alembic revision --autogenerate -m "change"
docker compose exec backend alembic upgrade head
```

## Rollback

```bash
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d --build   # pinned images
```

On Portainer: redeploy the previous stack definition / image tag. In a
migration, keep the old host running and flip DNS back to roll back — see
`server-migration.md`.
