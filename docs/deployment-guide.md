# Deployment Guide

## Deployment order (promotion policy) — MANDATORY

When a new update is pushed out, roll it out in this exact order. Do not skip or
reorder a tier:

1. **Demo** — `demo.autobrainservice.app` (public, low-risk, demo account).
2. **Default** — the default/dev environment (dev box, `docker-compose.yml` /
   `docker-compose.prod.yml` source mounts).
3. **Hosted** — `hosted.autobrainservice.app` (Oracle Cloud `152.69.188.133`,
   Portainer endpoint 5, `docker-compose.hosted.yml` prebuilt images).

Only promote to the next tier once the current one is verified healthy (startup,
health checks, key flows). A change never goes to Hosted without first passing
Demo and Default. Source of truth: board directive AUT-78.

### Release checklist (release is NOT complete until Hosted is verified last)

Every release runs the gates below, in order. No gate may be skipped; a failed
gate blocks the release at that tier.

- [ ] 0. **Code gate** — every feature/PR for this release is **merged to `main`
      first**. Do NOT deploy, promote, or announce a feature whose PR is still
      open or unmerged. A merged-but-unannounced feature still needs a deploy;
      an unmerged feature must not be deployed or changelogged. (AUT-121
      regression: AUT-21/AUT-115 sat in open PRs for hours while the changelog
      claimed the feature shipped — nothing reached any tier.)
- [ ] 1. **Demo** — deploy to `demo.autobrainservice.app`; verify startup +
      `/health` + key flows.
- [ ] 2. **Default** — deploy to dev/default (source mounts); verify startup +
      `/health` + key flows.
- [ ] 3. **Hosted** — deploy to `hosted.autobrainservice.app` (Oracle Cloud
      `152.69.188.133`, Portainer endpoint 5); verify startup + `/health` + key
      flows. **Only when this passes is the release complete.**
- [ ] **Verify the feature is actually present** on each tier — do not rely on
      the version banner alone. Exercise the flow (e.g. open the new screen,
      hit the new endpoint) or confirm the feature's UI strings/endpoints exist
      in the deployed build. (AUT-121 regression: frontends on Demo/Default
      were stale builds with no share feature while Hosted had a newer one.)
- [ ] Note promotion order + verification result in the issue / #updates channel.

## Prerequisites

- Linux host with Docker 24+ and Docker Compose v2.
- 4 vCPU / 8 GB RAM minimum for the full stack.
- `.env` populated from `.env.example`.

## One-time server setup

```bash
sudo ./scripts/setup-server.sh <user>
```

## Deploy (dev)

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
# Then update Portainer stack on endpoint 5 (AutoBrain-Hosted) to pull new images.
```

## Deploy (production)

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

## Kubernetes

```bash
kubectl apply -f infra/k8s/
kubectl -n autobrain rollout status deployment/autobrain-backend
```

## systemd (bare metal)

```bash
sudo cp infra/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now autobrain-backend
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
