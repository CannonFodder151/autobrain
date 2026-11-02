# AutoBrain Shop Deployment — Oracle VM (EP5)

## Overview

The AutoBrain Shop stack deploys on the Oracle Cloud VM at **152.69.188.133** (Portainer EP5) alongside the existing `autobrain-hosted` and `rego-lookup` stacks. All Shop images are pulled from a **self-hosted private Docker registry** running on the same VM.

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │        Oracle Cloud VM (EP5)             │
                    │        152.69.188.133                    │
                    │                                         │
   ┌──────┐        │  ┌─────────┐    ┌────────────────────┐  │
   │      │───────►│  │  NGINX  │───►│  Frontend (nginx)  │  │
   │ CF   │  :443  │  │  Proxy  │    │  :8087→8080        │  │
   │      │───────►│  └─────────┘    └────────────────────┘  │
   └──────┘        │       │           ┌────────────────────┐  │
                    │       │           │  Backend (API)     │  │
                    │       └──────────►│  :8000             │  │
                    │                   └────────────────────┘  │
                    │                   ┌────────────────────┐  │
                    │                   │  Celery Worker     │  │
                    │                   │  (separate svc)    │  │
                    │                   └────────────────────┘  │
                    │                   ┌────────────────────┐  │
                    │                   │  AI Gateway        │  │
                    │                   │  :8001             │  │
                    │                   └────────────────────┘  │
                    │                                         │
                    │  ┌──────────┐  ┌──────────┐  ┌───────┐  │
                    │  │ Postgres │  │  Redis   │  │ MinIO │  │
                    │  └──────────┘  └──────────┘  └───────┘  │
                    │                                         │
                    │  ┌──────────────────────────────────┐   │
                    │  │  Private Registry :5000          │   │
                    │  │  All shop images pulled from here │   │
                    │  └──────────────────────────────────┘   │
                    │                                         │
                    │  ┌──────────┐  ┌──────────┐             │
                    │  │ 9Router  │  │  Backup  │             │
                    │  │ :20129   │  │  :8081   │             │
                    │  └──────────┘  └──────────┘             │
                    └─────────────────────────────────────────┘
```

## First-Time Setup

### 1. Create secrets directory

```bash
# On the Oracle VM (via Portainer console or SSH from this box)
sudo mkdir -p /data/autobrain-shop/secrets
sudo chown root:1000 /data/autobrain-shop/secrets
sudo chmod 750 /data/autobrain-shop/secrets
```

### 2. Seed secrets

```bash
# Copy the stack env to a file, then run seed script
./scripts/seed-shop-secrets.sh /path/to/shop-env.txt /data/autobrain-shop/secrets
```

### 3. Generate registry htpasswd

```bash
# On the Oracle VM
docker run --rm --entrypoint htpasswd httpd:2 -Bbn admin REGISTRY_PASSWORD > /data/autobrain-shop/htpasswd
```

### 4. Create NGINX config

```bash
# Create nginx config for SSL termination
sudo mkdir -p /data/autobrain-shop/certs
# Copy the TLS cert/key for shop.autobrainservice.app to:
#   /data/autobrain-shop/certs/fullchain.pem
#   /data/autobrain-shop/certs/privkey.pem
```

### 5. Deploy via Portainer

1. Go to Portainer → Stacks → Add Stack
2. Name: `autobrain-shop`
3. Repository: set to `CannonFodder151/autobrain`, reference file `docker-compose.shop.yml`
4. Add stack env vars (see `.env.shop.example`)
5. Deploy

### 6. Build and push images

```bash
# Trigger the build-shop workflow via GitHub Actions
gh workflow run build-shop.yml \
  -f tag=latest \
  -f api_base_url=https://shop.autobrainservice.app/api/v1 \
  -f ws_base_url=wss://shop.autobrainservice.app/ws \
  -f registry=152.69.188.133:5000
```

Or push to `main` — the workflow auto-triggers.

## Stack Services

| Service | Port | Description |
|---------|------|-------------|
| registry | 5000 | Private Docker registry |
| postgres | 5432 (internal) | PostgreSQL 17 + pgvector |
| redis | 6379 (internal) | Redis 7.2 + password auth |
| minio | 9000 (internal) | Object storage (S3-compatible) |
| backend | 8000 (internal) | FastAPI + Celery worker+beat |
| ai-gateway | 8001 (internal) | AI gateway + market data |
| celery | — | Separate Celery worker (4 concurrency) |
| frontend-nginx | 8087 (internal) | Flutter web → nginx |
| dongle-server | 8000 (internal) | Firmware distribution |
| 9router | 20129 (host) | AI router (9Router) |
| autobrain-backup | 8081 (host) | Backup management GUI |
| nginx | 80/443 (public) | SSL reverse proxy |

## CI/CD Flow

1. Push to `main` (or manual trigger) → `build-shop.yml`
2. Builds `backend`, `ai`, `frontend` images per arch (amd64 + arm64)
3. Pushes to private registry at `152.69.188.133:5000`
4. Assembles multi-arch manifests
5. Syncs compose to Portainer stack

## Cloudflare DNS

Request these DNS records via Discord #ops:

| Type | Name | TTL | Content | Reason |
|------|------|-----|---------|--------|
| A | shop | 300 | 152.69.188.133 | Shop app domain |
| AAAA | shop | 300 | (IPv6 if available) | Dual-stack |

## Security Notes

- Private registry requires authentication (htpasswd)
- All secrets use the `*_FILE` pattern (AUT-1533)
- NGINX handles SSL termination with Let's Encrypt certs
- Registry is only exposed on port 5000 (not behind Cloudflare)
- Backend, celery, AI gateway are internal-only (not exposed to host)
- Frontend is behind nginx reverse proxy on 127.0.0.1:8087
