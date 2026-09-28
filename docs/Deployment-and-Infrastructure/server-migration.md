# Server Migration — Moving the Hosted Stack to Oracle Cloud

## Purpose

This runbook covers migrating the AutoBrain hosted stack from the on-prem Portainer box to the Oracle Cloud VM (`152.69.188.133`, Portainer EP5). It preserves users, vehicles, service/fuel/parts history, uploaded files, subscriptions, and federation data. Target downtime is under an hour.

**Status: MIGRATION COMPLETE (AUT-2409 / AUT-2411)** — The hosted stack is now running on Oracle Cloud. This document is retained as a reference for future migrations or disaster recovery.

## What needs to move

| Item | Where it lives | Required? |
|------|----------------|-----------|
| **Database** (users, vehicles, all records, federation) | Postgres named volume `postgres-data` | Yes |
| **Uploaded files** (receipts, photos, dongle firmware) | MinIO named volume `minio-data` | Yes |
| **Hub data** (federation registry) | Named volume `hub-data` | Yes |
| **9Router config** (providers, API keys) | External volume `9router-data` | Yes |
| **Cache / Celery results** | Redis named volume `redis-data` | No — safe to start fresh |
| **Stack definition** | Portainer stack file (`docker-compose.hosted.yml`) | Yes |
| **Secrets** | `/data/autobrain/secrets` on host (AUT-1533) — SECRET_KEY, STRIPE_*, AI_ROUTER_*, SMTP, MINIO creds, ADMIN_API_KEY, REGO_LOOKUP_*, FUEL_*, IAP_*, DONGLE_*, HUB_*, CI_TRIAGE_*, PAPERCLIP_* | Yes |

Keep `SECRET_KEY` unchanged so existing refresh tokens survive; keep `STRIPE_WEBHOOK_SECRET` and the Stripe price IDs unchanged so subscriptions keep working. Passwords are bcrypt-hashed, so they migrate as-is.

## Target environment (Oracle Cloud VM)

- **Host**: `152.69.188.133` (ARM64, Ubuntu Core 24)
- **Portainer endpoint**: 5 = AutoBrain-Hosted
- **Network**: Separate VCN — has its OWN 9Router instance, its OWN rego-lookup instance, its OWN federation hub instance.
- **Secrets path**: `/data/autobrain/secrets` (NOT `/opt/autobrain/secrets` — snap dockerd masks `/opt` read-only; see AUT-1853).
- **DNS**: `hosted.autobrainservice.app` / `hub.autobrainservice.app` via Cloudflare (managed by Deployment team).
- **Firewall**: `fw-keeper` container enforces host-level rules (Portainer agent `:9001` restricted to `122.199.30.128/32`; 9Router `:20128` restricted to `122.199.30.128/32` + `172.18.0.0/16`).

## Before you start

- New host prerequisites: Docker 24+ and Docker Compose v2, 4 vCPU / 8 GB RAM minimum.
- The target network has its **own** 9Router and Rego Lookup instances — point `AI_ROUTER_URL` / `REGO_LOOKUP_URL` at the local services on that network, not back at the old host.
- Pick a maintenance window. Take the backup while the stack is not receiving writes for a consistent snapshot.
- Ensure `/data/autobrain/secrets` is provisioned on the target host before deploy (see `docs/security.md` "Oracle VM path migration (AUT-1853)").

## Step 1 — Snapshot the old host

### Option A: Built-in full backup (recommended)

The admin backup serialises **every table** (including users with their bcrypt hashes and Stripe fields) into one portable JSON file.

1. Log in as admin → **User administration** → **Backup & restore**, or:

   ```bash
   curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     https://old-host/api/v1/admin/backup -o autobrain-backup.json
   ```

2. Copy the file off the server somewhere safe (it contains the full user DB — treat it as secrets).

This captures only the **database**. Uploaded files in MinIO and hub/9router data must be copied separately — see Option B.

### Option B: Full data fidelity (DB + files + hub + 9router) via volume copy

```bash
# PostgreSQL
docker run --rm -v autobrain_postgres-data:/from -v "$PWD/vol-postgres":/to \
  alpine sh -c 'cp -a /from/. /to/'

# MinIO
docker run --rm -v autobrain_minio-data:/from -v "$PWD/vol-minio":/to \
  alpine sh -c 'cp -a /from/. /to/'

# Hub data
docker run --rm -v autobrain_hub-data:/from -v "$PWD/vol-hub":/to \
  alpine sh -c 'cp -a /from/. /to/'

# 9Router data (external volume)
docker run --rm -v 9router-data:/from -v "$PWD/vol-9router":/to \
  alpine sh -c 'cp -a /from/. /to/'
```

Or a cleaner Postgres dump (transfers/compresses better):

```bash
docker compose -f docker-compose.hosted.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > autobrain.dump
```

Transfer everything (backup/volumes) to the new host with `scp`/`rsync`.

## Step 2 — Deploy on the new host (Oracle Cloud)

```bash
# On Oracle VM (or via Portainer stack deploy)
git clone https://github.com/CannonFodder151/autobrain.git
cd autobrain

# Provision secrets directory (AUT-1853)
sudo mkdir -p /data/autobrain/secrets
sudo chmod 0750 /data/autobrain/secrets
sudo chgrp 1000 /data/autobrain/secrets

# Seed secrets from stack env dump
sudo ./scripts/seed-secrets.sh /tmp/stack-env.txt /data/autobrain/secrets
shred -u /tmp/stack-env.txt

# Deploy stack via Portainer from docker-compose.hosted.yml
# Stack env must include: SECRETS_DIR=/data/autobrain/secrets
# Portainer: Stacks → autobrain-hosted → Update stack → pullImage: true
```

On first boot the backend runs Alembic migrations automatically (`python -m app.db.bootstrap`), then seeds the admin account from `ADMIN_EMAIL`/`ADMIN_INITIAL_PASSWORD` if it doesn't exist.

### Portainer

Create a **standalone stack** on endpoint 5 (AutoBrain-Hosted) with the `docker-compose.hosted.yml` definition and the secrets env inlined in the stack. Volume names are created fresh — restore into them before `up`, or restore through the app after.

## Step 3 — Restore data

- **Option A (JSON backup):** log in as admin on the new host → **Backup & restore** → upload → confirm. Restore wipes the fresh DB and re-inserts with original IDs. Then copy MinIO/hub/9router data separately.
- **Option B (volumes/dump):** pre-create volumes and restore before first `up`:

  ```bash
  docker volume create autobrain_postgres-data
  docker volume create autobrain_minio-data
  docker volume create autobrain_hub-data
  # 9router-data is external — create manually if needed
  docker volume create 9router-data

  # Restore volumes
  docker run --rm -v "$PWD/vol-postgres":/from -v autobrain_postgres-data:/to \
    alpine sh -c 'cp -a /from/. /to/'
  docker run --rm -v "$PWD/vol-minio":/from -v autobrain_minio-data:/to \
    alpine sh -c 'cp -a /from/. /to/'
  docker run --rm -v "$PWD/vol-hub":/from -v autobrain_hub-data:/to \
    alpine sh -c 'cp -a /from/. /to/'
  docker run --rm -v "$PWD/vol-9router":/from -v 9router-data:/to \
    alpine sh -c 'cp -a /from/. /to/'

  # Or pg_dump:
  docker compose -f docker-compose.hosted.yml up -d postgres
  docker compose -f docker-compose.hosted.yml exec -T postgres \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < autobrain.dump
  docker compose -f docker-compose.hosted.yml up -d
  ```

## Step 4 — Switch traffic

1. **DNS:** the site is fronted by Cloudflare. Change the `A` record for `hosted.autobrainservice.app` and `hub.autobrainservice.app` from the old host IP to `152.69.188.133`. Keep it proxied (orange-cloud) so TLS/Cloudflare settings don't change.
2. **Reverse proxy:** Nginx Proxy Manager on the Oracle VM already has proxy hosts configured — verify they point to the stack's frontend service name (which resolves to static IP `172.18.0.14`).
3. **Stripe:** webhooks + checkout redirects use the public hostname, so no Stripe changes unless the hostname changed.
4. **Rego Lookup:** hosted stack uses its own rego-lookup instance at `http://rego-lookup:8011` (loopback, stack-local). No DNS change needed.

## Step 5 — Verify

| Check | Command / where |
|-------|-----------------|
| All services up | `docker compose -f docker-compose.hosted.yml ps` (or Portainer stack view) |
| API healthy | `curl -fsS https://hosted.autobrainservice.app/health` |
| Login works | Log in with an existing account and with the admin account |
| Data present | A vehicle with photos, services, fuel history renders correctly |
| AI works | Run one AI diagnostic — confirm `model` is `9router` (router reachable) |
| Billing works | License screen shows current subscription; no re-payment needed |
| Federation works | Community Garage: `/admin/social/register` succeeds (hosted=true free license) |
| Dongle server | `GET /api/v1/dongle/firmware/latest` → 401 without auth (paid gate enforced) |
| Background jobs | Watch logs for the daily backup and notification beats |
| Backup health | `autobrain-backup` web GUI (`127.0.0.1:8080` via SSH tunnel) shows recent backups |

## Rollback

Keep the old host running (don't delete its volumes) until the new host has passed Step 5. To roll back, flip the DNS records back to the old host IP — nothing else changes.

## Secrets checklist for `.env` / Portainer stack env

`SECRET_KEY` · `STRIPE_SECRET_KEY` · `STRIPE_WEBHOOK_SECRET` ·
`STRIPE_PRICE_ENTHUSIAST_MONTHLY/YEARLY` · `STRIPE_PRICE_GARAGE_MONTHLY/YEARLY` ·
`AI_ROUTER_URL` (stack-local: `http://9router:20128/v1`) · `AI_ROUTER_API_KEY` · `AI_ROUTER_MODEL` ·
`SMTP_HOST/USERNAME/PASSWORD` ·
`MINIO_ACCESS_KEY/SECRET_KEY` ·
`ADMIN_API_KEY` · `REGO_LOOKUP_API_KEY` ·
`FUEL_NSW_API_KEY/SECRET` · `FUEL_VIC_API_KEY/SECRET` · `FUEL_QLD_API_KEY` · `FUEL_SA_API_KEY` ·
`IAP_GOOGLE_SERVICE_ACCOUNT_JSON` · `IAP_APPLE_ISSUER_ID/KEY_ID/PRIVATE_KEY` ·
`DONGLE_SERVER_API_KEY` · `DONGLE_WEB_BASIC_PASSWORD` ·
`HUB_STRIPE_SECRET_KEY` · `HUB_STRIPE_WEBHOOK_SECRET` · `HUB_STRIPE_PRICE_FEDERATION_YEAR` · `HUB_ADMIN_KEY` · `HUB_HOSTED_REGISTRATION_KEY` ·
`CI_TRIAGE_WEBHOOK_SECRET` · `CI_TRIAGE_PARENT_ISSUE_ID` · `CI_TRIAGE_GOAL_ID` · `CI_TRIAGE_AGENT_ID` ·
`PAPERCLIP_API_URL` · `PAPERCLIP_API_KEY` · `PAPERCLIP_COMPANY_ID` ·

Per-instance secret values are recorded in **Outline (internal-only)**, never in this repo. The secret-file pattern (AUT-1533) means the stack consumes `*_FILE` variants from `/data/autobrain/secrets` — plain env vars for secrets are not used.

---

**Related docs:** [`deployment-guide.md`](./deployment-guide.md) | [`infrastructure-diagrams.md`](./infrastructure-diagrams.md) | [`ci-cd.md`](./ci-cd.md) | [`backup-strategy.md`](./backup-strategy.md) | [`monitoring.md`](./monitoring.md) | [`security.md`](../Security/security.md)

**Graft usage:** This repo is indexed with Graft (trailhq/Graft). Run `graft map` to orient, `graft ask "<task>"` to find code, `graft grep "<regex>"` for exhaustive search, `graft callers <symbol>` for call graphs, `graft blast --base origin/main` for diff blast radius. See `AGENTS.md` for agent integration.