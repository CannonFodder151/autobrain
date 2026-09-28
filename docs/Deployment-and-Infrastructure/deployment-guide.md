# Deployment Guide

## Deployment order (promotion policy) — MANDATORY

**OVERRIDE ACTIVE (AUT-2409 / AUT-2411):** The AUT-107 three-tier promotion chain (Demo → Default → Hosted) is **PAUSED**. As of AUT-2409, **all deploys are hosted-only (Oracle Cloud `152.69.188.133`, Portainer endpoint 5) in the nightly 03:00–04:00 AEST window**. Do NOT deploy to Demo (`demo.autobrainservice.app`, EP2 demo stack) or Default (`default.autobrainservice.app`, EP2 default stack). Image prune across EP2+EP5 is still permitted; redeploy on EP2 is not. Out-of-window hosted deploys require explicit board approval.

This override re-scoped (AUT-2411): AUT-2407, AUT-2316, AUT-1001, AUT-2229, AUT-2152, AUT-2109. Cancelled: AUT-1783, AUT-2135. PRs in flight: autobrain#492, rego-lookup-api#50. When the override is lifted, revert to: 1) Demo, 2) Default, 3) Hosted with per-tier health gating per `docs/deployment-guide.md`.

### Release checklist (hosted-only)

Every release runs the gates below. No gate may be skipped; a failed gate blocks the release.

- [ ] 0. **Code gate** — every feature/PR for this release is **merged to `main` first**. Do NOT deploy a feature whose PR is still open or unmerged.
- [ ] 1. **Hosted build** — `build-hosted.yml` workflow completes on the Oracle VM self-hosted ARM64 runner, pushing multi-arch (`amd64` + `arm64`) images to `ghcr.io/cannonfodder151/autobrain-*:hosted`.
- [ ] 2. **Hosted deploy** — trigger `deploy-instances.yml` (`workflow_dispatch`) which runs `scripts/upgrade-instances.sh` against Portainer EP5 (`pullImage:true`). Stack: `autobrain-hosted`.
- [ ] 3. **Health verification** — `/health` on `https://hosted.autobrainservice.app/health` returns the new version; key flows verified.
- [ ] 4. **Post-deploy prune** — run `scripts/prune-images.sh` to drop dangling build-layer images on EP5 (AutoBrain-Hosted).
- [ ] 5. **Note verification result** in the issue / `#updates` channel via n8n Discord Reporter.

## Environment tiers

| Tier | URL | Host | Portainer EP | Images |
|------|-----|------|--------------|--------|
| **Hosted (Production)** | `hosted.autobrainservice.app` | Oracle Cloud VM `152.69.188.133` | 5 = AutoBrain-Hosted | `ghcr.io/cannonfodder151/autobrain-*:hosted` (multi-arch) |
| Demo | `demo.autobrainservice.app` | Portainer-Host `10.0.3.17` | 2 = Portainer-Host | **PAUSED** (AUT-2409) |
| Default | `default.autobrainservice.app` | Portainer-Host `10.0.3.17` | 2 = Portainer-Host | **PAUSED** (AUT-2409) |

Hosted runs as a standalone Portainer stack with prebuilt images pulled from GHCR. The stack sits behind Nginx Proxy Manager (`npm`) on the Oracle VM; the stack frontend nginx exposes `:8080` (container) → `127.0.0.1:8086` (host), proxied by npm on `:443` via Cloudflare.

## Deployment log (hosted)

| Date | Version | Change | Verified |
|------|---------|--------|----------|
| 2026-08-27 | d946fe9 (PR #300, AUT-1673 paid-account gate) | Hosted (EP5) `ghcr.io/...:hosted` (d946fe9 build). Backend env wired to dongle-server backchannel: added `DONGLE_SERVER_API_KEY` + `DONGLE_SERVER_URL: http://dongle-server:8000`. PullImage:false after pre-pulling fresh images (proxy 60s timeout blocks blocking PullImage:true); hosted app containers force-recreated. | Hosted `/health` → v0.3.144. Paid gate `GET /api/v1/dongle/firmware/latest` unauth → **401** (require_premium enforced). Backchannel `POST /api/v1/devices/verify` unauth → **401 "Invalid or missing internal API key"** (was 503). |

## Stack services (Hosted — `docker-compose.hosted.yml`)

| Service | Image | Notes |
|---------|-------|-------|
| postgres | `pgvector/pgvector:pg17@sha256:cf134a7...` | healthcheck `pg_isready`; volume `postgres-data`; **non-root** (read_only, cap_drop ALL, tmpfs) |
| redis | `redis:7.2.5-alpine@sha256:6aaf3f5...` | healthcheck authenticated; volume `redis-data`; **non-root**, `--requirepass` from secret file |
| minio | `minio/minio@sha256:14cea49...` | pinned (AUT-322); bucket init in entrypoint (no `minio-init` sidecar); **non-root**; volume `minio-data` |
| backend | `ghcr.io/.../autobrain-backend:hosted@sha256:145438...` | **Unified**: API `:8000` + Celery worker+beat (AUT-3153) + AI gateway **NOT** here (separate `ai` service); **non-root**; static IP `172.18.0.15` |
| ai | `ghcr.io/.../autobrain-ai:hosted@sha256:c58a7c...` | AI gateway `:8001` + market-data `:8000`; **non-root**; `shm_size: 256m` for Chromium |
| dongle-server | `ghcr.io/.../autobrain-dongle-server:hosted@sha256:c57689...` | Firmware/distribution for OBD ESP32 dongles (AUT-1673); shares MinIO/Postgres; **non-root** |
| frontend | `ghcr.io/.../autobrain-frontend:hosted@sha256:02ed10...` | nginx-unprivileged `:8080` → `127.0.0.1:8086`; **non-root**; static IP `172.18.0.14`; healthcheck probes backend `/health` |
| hub | `ghcr.io/.../autobrain-federation-hub:hosted@sha256:d1d9bd...` | Community Garage federation hub (AUT-333/532); private repo; volume `hub-data`; `SOCIAL_FEDERATION_HOSTED=true` (free bundled license) |
| gh-runner | `ghcr.io/actions/actions-runner:latest` | GitHub Actions ARM64 self-hosted runner (AUT-2469); `privileged`, docker.sock bind; PAT from secret file |
| 9router | `decolua/9router:0.5.55@sha256:f00fe38...` | **Stack-local 9Router** (Oracle VM has its own instance); published `0.0.0.0:20128` but firewalled to dev egress IP `122.199.30.128/32` + docker subnet `172.18.0.0/16`; volume `9router-data` **external** |
| autobrain-backup | `ghcr.io/.../autobrain-backup:hosted@sha256:e76fac3...` | Web GUI for backup mgmt, restore, retention; `127.0.0.1:8080`; volumes `/data/autobrain-backup/{config,data}` |
| backup-agent | `ghcr.io/.../autobrain-backup-agent:hosted@sha256:59f26b...` | Hourly poller pulling DB snapshots from backend `/api/v1/admin-api/backup`; pushes to autobrain-backup ingest |

**Total containers: 12** (down from 9 pre-consolidation; worker merged into backend, dongle-server/gh-runner/hub/backup services added).

### Key architectural notes

- **PostgreSQL + pgvector**: `pgvector/pgvector:pg17` pinned by digest for multi-arch immutability across Demo/Default (x64) and Hosted (arm64).
- **Non-root containers**: All app services run with `read_only: true`, `cap_drop: [ALL]`, `tmpfs` mounts — hardened per AUT-1533/CIS.
- **Secret-file pattern (AUT-1533)**: Secret-class values live in `${SECRETS_DIR:-/data/autobrain/secrets}/<name>` on host (`root:1000`, `0640`), bind-mounted read-only at `/run/secrets`. At container start, `docker/lib-load-secrets.sh` exports `FOO_FILE` → `FOO` and derives authenticated `REDIS_URL`/`CELERY_*_URL`. Values never appear in `docker inspect` or `/proc/*/environ`. Redis uses `--requirepass` from secret; Postgres/MinIO use native `*_FILE` support.
- **Federated hub**: Community Garage hub runs as sibling service `hub` in the same stack. Backend registers via `SOCIAL_FEDERATION_HUB_URL` (default `https://hub.autobrainservice.app`); `SOCIAL_FEDERATION_HOSTED=true` on this stack (free bundled license per docs R5a).
- **Network pinning (AUT-372)**: Default network subnet `172.18.0.0/16` gateway `172.18.0.1`; frontend pinned to `172.18.0.14`, backend to `172.18.0.15`. Host-level npm caches frontend IP — static IP prevents 502 on frontend recreate.
- **9router external volume**: `9router-data` is **external** (created by original standalone container) — keep external so provider/API-key config persists across recreates.
- **No `worker` service**: Celery worker+beat run as background process in `backend` container (AUT-3153), matching `docker-compose.prod.yml`. Dedicated `autobrain-worker` image retired from CI (AUT-3172).

## Prerequisites (Hosted)

- Oracle Cloud VM (ARM64) with Docker 24+ and Docker Compose v2.
- 4 vCPU / 8 GB RAM minimum.
- Portainer agent connected to central Portainer (`https://portainer.nathanmartina.com`, endpoint 5).
- `/data/autobrain/secrets` provisioned with all secret files (see `scripts/seed-secrets.sh`).
- Cloudflare DNS for `hosted.autobrainservice.app` / `hub.autobrainservice.app` managed by Deployment team (no API key stored — DNS changes posted to Discord for Nathan to apply).

## One-time server setup (Oracle VM)

```bash
# Provision secrets directory (AUT-1853: /data not /opt)
sudo mkdir -p /data/autobrain/secrets
sudo chmod 0750 /data/autobrain/secrets
sudo chgrp 1000 /data/autobrain/secrets

# Seed secrets from stack env dump (obtained from Portainer stack env)
sudo ./scripts/seed-secrets.sh /tmp/stack-env.txt /data/autobrain/secrets
shred -u /tmp/stack-env.txt

# Ensure Portainer stack env has SECRETS_DIR=/data/autobrain/secrets
# Deploy stack via Portainer from docker-compose.hosted.yml
```

## Deploy (hosted) — the upgrade path (AUT-1847)

**Always use the GitHub Actions runner on the Oracle VM** to build hosted images (do NOT build locally). The `build-hosted.yml` workflow (on every merge to `main`, or via `workflow_dispatch`) builds multi-arch images on the self-hosted runners (x64 + ARM64 on the Oracle VM) and pushes them to ghcr.io with the `:hosted` tag.

Deployment is **owned by the Deployment Lead**, not automatic (board direction, AUT-1847): after `build-hosted.yml` completes, CI posts a Discord `#ops` notification (author "Deployment Lead") that an image is published and ready to promote. The Deployment Lead then triggers the `deploy-instances.yml` workflow (`workflow_dispatch`), which runs the upgrade path:

1. `scripts/upgrade-instances.sh` redeploys the Portainer stack via `PUT /api/stacks/{id}?endpointId=5&pullImage=true`, preserving stack env and volumes (`Prune: false`).
2. Tier is health-checked (`/health`); a failed tier stops the rollout.
3. DB migrations run on backend boot (`python -m app.db.bootstrap`), so a redeploy is a full upgrade.
4. `scripts/prune-images.sh` drops dangling images on EP5 after success.

```bash
# Manual run (hosted only):
UPGRADE_TIERS="autobrain-hosted|5|https://hosted.autobrainservice.app/health|" \
  ./scripts/upgrade-instances.sh
```
Run from the repo checkout on a host that can reach Portainer (the `deploy-instances.yml` `upgrade` job does exactly this, with `PORTAINER_API_KEY`/`PORTAINER_URL` repo secrets injected by GitHub).

Portainer stack updates pull images (`pullImage=true`) and recreate changed services. This is intended so CI-published images reach the tier, and it is safe for the frontend because the stack pins a static IP.

### Prerequisites for the Portainer API path (verified before relying on upgrade path)

- The Portainer agent on EP5 must accept container start operations against the host Docker Engine. **Hosted (EP5, Oracle VM) was previously blocked**: its agent (2.39.5) sent a request body to `POST /containers/{id}/start` that Docker 29.6.1 rejected, and the agent's `/opt` bind was read-only. **Resolved**: agent upgraded to 2.45-compatible version.
- The Hosted Portainer stack env must carry required non-secret vars (`POSTGRES_USER`, `POSTGRES_DB`) and Paperclip identity (`PAPERCLIP_API_KEY`, `CI_TRIAGE_WEBHOOK_SECRET`). `docker-compose.hosted.yml` defaults the DB vars so a redeploy never fails at interpolation even if the env is incomplete.
- Secret path (AUT-1853): `docker-compose.hosted.yml` defaults `SECRETS_DIR` to `/data/autobrain/secrets`. The Hosted Portainer stack env should set `SECRETS_DIR=/data/autobrain/secrets` (or rely on the compose default); never `/opt/autobrain/secrets` — the snap dockerd masks `/opt` read-only. Before redeploying the Hosted stack, provision + re-seed `/data/autobrain/secrets` (see `docs/security.md` "Oracle VM path migration (AUT-1853)"), then remove the legacy `autobrain-opt-guard.sh` `/opt` remount cron workaround.

### Nginx Proxy Manager + the hosted frontend (AUT-372)

Hosted sits behind a host-level Nginx Proxy Manager (`npm`) container that is **on the same Compose network** and forwards to the frontend service name. npm caches the resolved frontend container IP and does NOT re-resolve it, so a recreated frontend with a new IP returns 502 until npm is restarted.

Durable fix applied to `docker-compose.hosted.yml` and the live `autobrain-hosted` stack:
- Default network declares `subnet: 172.18.0.0/16` / `gateway: 172.18.0.1` (matches live network, so compose never recreates it).
- `frontend` service pins `ipv4_address: 172.18.0.14`.

Any frontend recreate keeps the same IP, so npm's cached value stays correct and the site stays up with **no npm restart** (verified: full frontend container recreate, site 200, npm untouched).

Rules:
- Do **not** remove the `networks` / `ipv4_address` block from the hosted compose.
- Do **not** point the npm proxy host at `152.69.188.133:8086` or the docker gateway IP: the Oracle host firewall drops hairpin/gateway traffic from npm (`EHOSTUNREACH`), so container-name forwarding to the static IP is the only stable target.
- npm, `9router`, and `rego-lookup` are attached to `autobrain-hosted_default` as external containers; never let compose try to recreate that network (marking it `external` or changing its IPAM fails or tears the stack down).

## Security: management surface lockdown (AUT-473)

The AutoBrain-Hosted VM (`152.69.188.133`) exposed several management/origin surfaces directly to the internet. Fixed and enforced via compose:

- **`9router` (`:20128`)** — published on `0.0.0.0:20128` so it is reachable from the host's public interface. It is locked down by the host firewall (`fw-keeper`, see `docs/security.md`): ingress on `:20128` is allowed only from the allow-listed dev egress IP (`122.199.30.128`) and the internal docker subnet (`172.18.0.0/16`); everything else is dropped. Backend/ai call it over the docker network (`http://9router:20128/v1`), which is unaffected by the host binding. The internal-subnet allow is required because backend consumes this service directly. Data volume `9router-data` is **external** — keep it external, never let compose create a fresh prefixed volume or the provider/API-key config is lost.
- **`frontend` origin (`:8086`)** — bound to `127.0.0.1` only. All client traffic goes through Cloudflare → npm (`:443`), which proxies to the frontend over the docker network. Never re-expose `8086` to `0.0.0.0`; that was a plaintext origin bypassing Cloudflare's WAF/rate limiting.
- **Port `:80`** — remediated (AUT-1744): a custom `default_server` block in `/data/nginx/custom/http.conf` returns `301 https://$host$request_uri`, so ALL plaintext `:80` traffic is redirected to HTTPS and the NPM "Default Site" welcome page is no longer served (kills the NPM version/CVE fingerprint). Both proxy hosts (`hosted.`, `hub.autobrainservice.app`) already have Force SSL, so their `:80` requests 301 as well. The NPM admin UI (`:81`) stays locked down / not internet-exposed, so the fix lives in the custom config, not the DB.
- **TLS/HSTS** — confirmed: HSTS `max-age=31536000; includeSubDomains; preload` at the Cloudflare edge; origin `:443` serves TLS.
- **Residual (needs OCI security list)** — `:9001` Portainer agent must stay reachable from the central Portainer host; restrict the OCI ingress rule for `9001` to the Portainer host IP only. `22`/`443` remain open (SSH + TLS).

Redeploy rule: keep these localhost bindings and the external `9router-data` volume in `docker-compose.hosted.yml` and the live stack; a stack deploy that reverts them re-opens the exposed surface.

## Deploy (production, from source) — self-hosted reference

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

## Migrations

First boot runs `python -m app.db.bootstrap` (Alembic, falling back to `create_all`). Afterwards use Alembic:

> **Resolved (AUT-510) — create_all-hybrid DBs.** A DB that was ever bootstrapped via the `create_all` fallback (Alembic failure) has tables Alembic has never seen. From v0.3.43+ the social migrations are linear and idempotent: `n4p5q6r7s8t9` was reparented onto `a5b6c7d8e9f0` (fixing the two-head fork that made `alembic upgrade head` fail with "Multiple head revisions"), and every DDL op in `n4p5q6r7s8t9` / `p6q7r8s9t0u1` is guarded so already-present tables and columns are skipped. The v0.3.41 manual `ALTER TABLE`s are now no-ops.
>
> New columns on existing tables still require a real Alembic migration (never rely on `create_all` — it only creates missing *tables*).
>
> **Production must NEVER fall back to `init_db()`.** The bootstrap at `app/db/bootstrap.py` runs `alembic upgrade head`; if that fails (e.g. a broken migration like AUT-2482's `op.get_inspector()` crash on `aut1859_fuel_price_alerts.py`) it silently falls back to `Base.metadata.create_all`, which only emits *missing tables* — it cannot add new columns, partial unique indexes, or any DDL Alembic was meant to apply. The first symptom is a runtime `UndefinedColumnError` (e.g. `column notification_deliveries.user_id does not exist`) on a Celery task that reads the table — not at boot. If you ever see `alembic_failed_falling_back_to_create_all` in backend logs on a hosted environment, the deploy is broken: stop, fix the migration, re-run `alembic upgrade head` via the backend bootstrap path (`python -m app.db.bootstrap`), and verify the worker log carries `alembic_migrations_applied` on the next boot. Do not paper over it with `create_all`. Reproduce the broken state with `docker compose -f docker-compose.hosted.yml run --rm backend alembic upgrade head` from a workstation against a clone of the hosted DB (redacted secrets) before shipping a fix.

```bash
docker compose exec backend alembic revision --autogenerate -m "change"
docker compose exec backend alembic upgrade head
```

## Rollback

On Portainer: redeploy the previous stack definition / image tag (use `hosted-sha-<commit>` tags for precise rollback). In a migration, keep the old host running and flip DNS back to roll back — see `server-migration.md`.

---

**Related docs:** [`ci-cd.md`](./ci-cd.md) | [`infrastructure-diagrams.md`](./infrastructure-diagrams.md) | [`server-migration.md`](./server-migration.md) | [`backup-strategy.md`](./backup-strategy.md) | [`monitoring.md`](./monitoring.md) | [`autobrain-deploy-trigger.md`](./autobrain-deploy-trigger.md) | [`security.md`](../Security/security.md)

**Graft usage:** This repo is indexed with Graft (trailhq/Graft). Run `graft map` to orient, `graft ask "<task>"` to find code, `graft grep "<regex>"` for exhaustive search, `graft callers <symbol>` for call graphs, `graft blast --base origin/main` for diff blast radius. See `AGENTS.md` for agent integration.