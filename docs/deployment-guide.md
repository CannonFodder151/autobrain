# Deployment Guide

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

## Deploy (production)

```bash
cp .env.example .env   # fill real values, especially SECRET_KEY + AI_ROUTER_URL
docker compose -f docker-compose.prod.yml up -d --build
```

Prod runs behind nginx on port 80:
- `/api/*` → backend
- `/ws/*`  → backend WebSocket
- `/ai/*`  → AI gateway
- `/`      → Flutter web build (mount a build or use the frontend image)

## Over SSH

```bash
./scripts/deploy.sh administrator@10.0.3.39
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
