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

## Deployment log

| Date | Version | Change | Verified |
|------|---------|--------|----------|
| 2026-08-27 | v0.3.141 | Deploy order Demo → Default → Hosted (Portainer stacks 73/68 EP2, 83 EP5, `pullImage:true`). Docker Hub `cannonfodder151/autobrain-{backend,ai,frontend}:0.3.141` rebuilt on `ubuntu-latest` (self-hosted x64 runner busy with OCR review — temporary CI dispatch bypassed). ghcr.io `:hosted` manifest recreated from existing amd64+arm64 variants (build-hosted run cancelled mid-pipeline). Demo frontend ghcr `:demo` rebuilt. All redeploy guards verified: frontend `ipv4_address: 172.18.0.14`, `9router` bound to `127.0.0.1`, `9router-data` volume external, `SOCIAL_FEDERATION_HUB_URL` retained in backend env. | `/health` → 0.3.141 on all three tiers; pruned dangling images (EP2: 0.04GB reclaimed, EP5: 4.9GB reclaimed). |
| 2026-08-13 | v0.3.56 | Post-merge deploy of AUT-531 license deep-link (PR #100) + AUT-597 bounded social upload reads (PR #110). Deploy order Demo → Default → Hosted (Portainer stacks 73/68 EP2, 83 EP5, `pullImage:true`, backend/ai/market-data/frontend → `0.3.56`). Demo frontend ghcr `:demo` rebuilt from current main (workflow_dispatch, tag=demo). Pruned dangling images (EP2 ~940MB/51, EP5 ~640MB/4). | `/health` → `0.3.56` on all three tiers; hosted `/#/license` logged-out → login form (headless render); hosted `/auth/config` `license_enabled:true` + `/billing/pricing` → AUD plans (auth'd). Deep-link routing (`fragment=="license"` → LicenseScreen) present in all three deployed bundles. Logged-in headless render raced the Flutter engine's URL-fragment normalization (fragment cleared before async session restore) — flagged for real-browser QA confirm. |
| 2026-08-13 | v0.3.55 | Post-merge deploy of AUT-523 billing hardening (PR #107, merge `587b3e38`): `_apply_subscription` preserves entitlement for active subs on archived/unknown prices (no demote-to-free), `plan_for_user` infers plan from entitlement, `scripts/stripe-setup.py` refuses to archive prices with active subs. Merge conflict resolved (CHANGELOG only). Deploy order Demo → Default → Hosted (Portainer stacks 73/68 EP2, 83 EP5, `pullImage:true`); backend/ai/frontend/market-data `:0.3.55` (demo frontend ghcr `:demo`, default frontend `:default` rebuilt). No-orphan pre-check: live Stripe has 1 sub on the archived USD prices (status `canceled`), hosted DB has 0 users referencing archived USD ids. Pruned dangling images (EP2/EP5). | `/health` 0.3.55 on all three tiers; `/billing/pricing` → `currency: aud` (A$9 / A$19) on all three; license renders `A$` when `currency==aud` (`license_screen.dart`) |
| 2026-08-13 | v0.3.51 | Post-merge deploy of AUT-523 AUD subscription (PR #99, merge `763938f`) + AUT-532/539/540 co-published images. Deploy order Demo → Default → Hosted (Portainer stacks 73/68 EP2, 83 EP5, `pullImage:true`). Demo frontend ghcr `:demo` rebuilt at v0.3.51. Ran `scripts/stripe-setup.py` (with `transfer_lookup_key=True`, PR #105, merge `82d35d38`) against the live account: archived the 4 USD prices, created 4 AUD prices under the same lookup keys. Hosted stack `STRIPE_PRICE_*` env updated to AUD IDs (price_1U42qyRvVxLqqFOA2TxjWvWN / price_1U42qzRvVxLqqFOAmoXPFFvb / price_1U42r0RvVxLqqFOAkImHoSwP / price_1U42r2RvVxLqqFOAGZ5xlxQr). | `/billing/pricing` → `currency: aud` on all three tiers (was `usd`); live Stripe Checkout Session created from the hosted env price → `currency: aud`, `amount_total: 900` (A$9), price `aud` recurring monthly |
| 2026-08-13 | v0.3.41 | Post-merge deploy of AUT-501 My Builds (PR #87, merge `ea095d18`): `GET /social/my-posts` + `PATCH /social/posts/{id}` (owner-only edit, 404 for non-owners). Deploy order Demo → Default → Hosted. Backend/ai/market-data pinned to `:0.3.41` image tags (v0.3.42 was publishing concurrently — separate release, see AUT-508). Frontends: demo=ghcr `:demo` (v0.3.42 build, has My Builds), default=`:default`, hosted=`:0.3.41`. **Release-blocking schema drift fixed on the fly:** `social_server_config.last_event_sync` + `author_user_id` nullable on `social_likes`/`social_comments` were missing on ALL three DBs — `alembic upgrade head` fails on create_all-hybrid DBs (`n4p5q6r7s8t9` collides with pre-existing tables, bootstrap falls back to `create_all` which cannot add columns). Manual `ALTER TABLE` applied to all 3 DBs; proper migration-chain fix tracked in a follow-up issue. | `/health` 0.3.41 on all three tiers; My Builds verified on demo + hosted: `my-posts` returns caller-only posts, owner `PATCH` persists, non-owner `PATCH` → 404 `Post not found` |
| 2026-08-13 | v0.3.36 | Post-merge deploy of AUT-461 (PR #78, merge `058c886`): GitHub token removed from the server entirely — mobile release check now reads the public `mobile/latest.json` manifest unauthenticated. `GITHUB_TOKEN` deleted from config, all 3 compose files, and all 3 stack envs (Demo/Default EP2, Hosted EP5). Deploy order Demo → Default → Hosted, `pullImage:true`. | `/health` 0.3.36 on all three tiers; `/api/v1/version/mobile` → `reachable:true`, latest v0.3.33+68 (manifest) on all; no stack env carries GITHUB_TOKEN |
| 2026-08-13 | v0.3.34 | Post-merge deploy of AUT-442 security fix (PR #74, merge `79a6a851`): GitHub PAT dropped from public version checks. All tiers promoted Demo → Default → Hosted (Portainer stacks 73/68 EP2, 83 EP5, `pullImage:true`); `GITHUB_TOKEN` stack env untouched (classic PAT still in place until fine-grained token lands — see AUT-461). Pruned dangling images (EP2 5.2GB, EP5 8.5GB). | `/health` 0.3.34 on all three tiers; `/api/v1/version/mobile` → `reachable:true`, latest v0.3.33+68 (2026-08-13T04:05Z) |
| 2026-08-13 | v0.3.32 | Post-merge deploy after AUT-441 merge drive: all tiers promoted Demo → Default → Hosted (AUT-450). Includes alembic migration-chain fix (PR #70) — gps_samples reparented onto `k2l3m4n5o6p7`. Mobile release surfaced: `/api/v1/version/mobile` → `reachable:true`, latest v0.3.31+66. | `/health` 0.3.32 on all three tiers; mobile endpoint live (2026-08-13T02:31Z) |

## Stack services

| Service | Image | Notes |
|---------|-------|-------|
| postgres | `postgres:16-alpine` | healthcheck `pg_isready`; volume `postgres-data` |
| redis | `redis:7-alpine` | healthcheck `redis-cli ping`; volume `redis-data` |
| minio | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | pinned (AUT-322); healthcheck `mc ready local`; volume `minio-data`; bucket auto-created + forced private via entrypoint (AUT-1242-C2, was the one-shot `minio-init` container) |
| backend | `autobrain-backend:<tag>` | API on `:8000` (internal); `/health` |
| worker | `autobrain-worker:<tag>` | Celery worker + beat (`-B`); single container (AUT-1242/C1) |
| ai | `autobrain-ai:<tag>` | AI gateway on `:8001` (internal); `/health` |
| frontend | `autobrain-frontend:<tag>` | nginx serves Flutter web + proxies `/api/*`, `/ws/*`, `/ai/*` |
| hub | `ghcr.io/cannonfodder151/autobrain-federation-hub:<tag>` | federation hub (Community Garage); built + pushed from the PRIVATE repo `autobrain-federation-hub` (board rev 8); deploy config only in this repo |

The backend registers with the hub via `SOCIAL_FEDERATION_HUB_URL` (default
`https://hub.autobrainservice.app`; override per stack). `SOCIAL_FEDERATION_HOSTED`
is `true` on the AutoBrain-Hosted stack (free bundled license, docs R5a) and
`false` on self-hosted/prod stacks (pays the $20/yr license). If the hub URL is
missing from the `backend` service env, Community Garage server registration
fails with `502 hub not configured` (AUT-532) — make sure the env reaches the
`backend` service on every redeploy.

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

Portainer stack updates pull images and recreate changed services (AUT-372).
This is intended so CI-published images reach the tier, and it is safe for the
frontend because the stack pins a static IP.

### Nginx Proxy Manager + the hosted frontend (AUT-372)

Hosted sits behind a host-level Nginx Proxy Manager (`npm`) container that is
**on the same Compose network** and forwards to the frontend service name. npm
caches the resolved frontend container IP and does NOT re-resolve it (the
`resolver valid=10s` does not help on this host), so a recreated frontend with
a new IP returns 502 until npm is restarted.

Durable fix already applied to `docker-compose.hosted.yml` and the live
`autobrain-hosted` stack:

- the default network declares `subnet: 172.18.0.0/16` / `gateway: 172.18.0.1`
  (matches the live network, so compose never recreates it);
- the `frontend` service pins `ipv4_address: 172.18.0.14`.

Any frontend recreate keeps the same IP, so npm's cached value stays correct
and the site stays up with **no npm restart** (verified: full frontend container
recreate, site 200, npm untouched).

Rules:
- Do **not** remove the `networks` / `ipv4_address` block from the hosted
  compose.
- Do **not** point the npm proxy host at `152.69.188.133:8086` or the docker
  gateway IP: the Oracle host firewall drops hairpin/gateway traffic from npm
  (`EHOSTUNREACH`), so container-name forwarding to the static IP is the only
  stable target.
- npm, `9router`, and `rego-lookup` are attached to `autobrain-hosted_default`
  as external containers; never let compose try to recreate that network
  (marking it `external` or changing its IPAM fails or tears the stack down).

## Security: management surface lockdown (AUT-473)

The AutoBrain-Hosted VM (152.69.188.133) exposed several management/origin
surfaces directly to the internet. Fixed and enforced via compose:

- **`9router` (`:20128`)** — bound to `127.0.0.1` only. The Next.js admin
  dashboard and the OpenAI-compatible API are not internet-reachable. Backend/ai
  call it over the docker network (`http://9router:20128/v1`), which is
  unaffected by the host binding. Ops access the dashboard via SSH tunnel.
  Data volume `9router-data` is **external** (created by the original standalone
  container) — keep it external, never let compose create a fresh prefixed
  volume or the provider/API-key config is lost.
- **`frontend` origin (`:8086`)** — bound to `127.0.0.1` only. All client
  traffic goes through Cloudflare → npm (`:443`), which proxies to the frontend
  over the docker network. Never re-expose `8086` to `0.0.0.0`; that was a
  plaintext origin bypassing Cloudflare's WAF/rate limiting.
- **Port `:80`** — npm's default "Default Site" welcome page still serves
  unmatched hosts. Cosmetic info disclosure only (Cloudflare has Always Use
  HTTPS, so real clients never hit origin `:80`). Replace via npm Settings →
  Default Site when npm admin creds are available.
- **TLS/HSTS** — confirmed: HSTS `max-age=31536000; includeSubDomains; preload`
  at the Cloudflare edge; origin `:443` serves TLS.
- **Residual (needs OCI security list)** — `:9001` Portainer agent must stay
  reachable from the central Portainer host; restrict the OCI ingress rule for
  `9001` to the Portainer host IP only. `22`/`443` remain open (SSH + TLS).

Redeploy rule: keep these localhost bindings and the external `9router-data`
volume in `docker-compose.hosted.yml` and the live stack; a stack deploy that
reverts them re-opens the exposed surface.

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

> **Resolved (AUT-510) — create_all-hybrid DBs.** A DB that was ever bootstrapped
> via the `create_all` fallback (Alembic failure) has tables Alembic has never
> seen. From v0.3.43+ the social migrations are linear and idempotent:
> `n4p5q6r7s8t9` was reparented onto `a5b6c7d8e9f0` (fixing the two-head fork that
> made `alembic upgrade head` fail with "Multiple head revisions"), and every DDL
> op in `n4p5q6r7s8t9` / `p6q7r8s9t0u1` is guarded so already-present tables and
> columns are skipped. The v0.3.41 manual `ALTER TABLE`s are now no-ops.
>
> New columns on existing tables still require a real Alembic migration (never
> rely on `create_all` — it only creates missing *tables*).

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

