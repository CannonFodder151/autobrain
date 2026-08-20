# Server Migration — Moving the Stack to a New Linux Host

## Purpose

This runbook covers picking up the entire AutoBrain stack (backend, AI gateway,
worker, Postgres, Redis, MinIO) from the current host and re-deploying it
on another Linux host — typically the move from the on-prem Portainer box to a
cloud VPS. It preserves users, vehicles, service/fuel/parts history, uploaded
files and subscriptions. Target downtime is under an hour.

## What needs to move

| Item | Where it lives | Required? |
|------|----------------|-----------|
| **Database** (users, vehicles, all records) | Postgres named volume `postgres-data` | Yes |
| **Uploaded files** (receipt images, stored backups) | MinIO named volume `minio-data` | Yes |
| **Cache / Celery results** | Redis named volume `redis-data` | No — safe to start fresh |
| **Stack definition** | Portainer stack file (or `docker-compose.*.yml`) | Yes |
| **Secrets** | Portainer stack env (or `.env`) — SECRET_KEY, STRIPE_*, AI_ROUTER_*, SMTP, MINIO creds, ADMIN_API_KEY, REGO_LOOKUP_* | Yes |

Keep `SECRET_KEY` unchanged so existing refresh tokens survive; keep
`STRIPE_WEBHOOK_SECRET` and the Stripe price IDs unchanged so subscriptions keep
working. Passwords are bcrypt-hashed, so they migrate as-is.

## Before you start

- New host prerequisites: Docker 24+ and Docker Compose v2, 4 vCPU / 8 GB RAM
  minimum.
- Decide the post-migration public hostname. If it stays the same, nothing else
  changes — Stripe webhooks and checkout redirects keep working. If it changes,
  also update `APP_BASE_URL`, the Stripe webhook endpoint URL, and rebuild the
  frontend with the new `API_BASE_URL`/`WS_BASE_URL`.
- The target network may have its **own** 9Router and Rego Lookup instances —
  point `AI_ROUTER_URL` / `REGO_LOOKUP_URL` at the local services on that
  network, not back at the old host.
- Pick a maintenance window. Take the backup while the stack is not receiving
  writes for a consistent snapshot.

## Step 1 — Snapshot the old host

### Option A: built-in full backup (recommended)

The admin backup serialises **every table** (including users with their bcrypt
hashes and Stripe fields) into one portable JSON file.

1. Log in as admin → **User administration** → **Backup & restore**, or:

   ```bash
   curl -H "Authorization: Bearer $ADMIN_TOKEN" \
     https://old-host/api/v1/admin/backup -o autobrain-backup.json
   ```

2. Copy the file off the server somewhere safe (it contains the full user DB —
   treat it as secrets).

This captures only the **database**. Uploaded files in MinIO must be copied
separately — see Option B.

### Option B: full data fidelity (DB + files) via volume copy

```bash
docker run --rm -v autobrain_postgres-data:/from -v "$PWD/vol-postgres":/to \
  alpine sh -c 'cp -a /from/. /to/'
docker run --rm -v autobrain_minio-data:/from -v "$PWD/vol-minio":/to \
  alpine sh -c 'cp -a /from/. /to/'
```

Or a cleaner Postgres dump (transfers/compresses better):

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > autobrain.dump
```

Transfer everything (backup/volumes) to the new host with `scp`/`rsync`.

## Step 2 — Deploy on the new host

```bash
git clone https://github.com/CannonFodder151/autobrain.git
cd autobrain
cp .env.example .env        # then copy your real .env values over the top
docker compose -f docker-compose.prod.yml up -d --build
```

On first boot the backend runs Alembic migrations automatically
(`python -m app.db.bootstrap`), then seeds the admin account from
`ADMIN_EMAIL`/`ADMIN_INITIAL_PASSWORD` if it doesn't exist.

### Portainer

Create a **standalone stack** on the target endpoint with the same compose
definition and a fresh copy of the secrets (env inlined in the stack). Volume
names are created fresh — restore into them before `up`, or restore through the
app after.

## Step 3 — Restore data

- **Option A (JSON backup):** log in as admin on the new host → **Backup &
  restore** → upload → confirm. Restore wipes the fresh DB and re-inserts with
  original IDs. Then copy MinIO data separately.
- **Option B (volumes/dump):** pre-create volumes and restore before first `up`:

  ```bash
  docker volume create autobrain_postgres-data
  docker volume create autobrain_minio-data
  docker run --rm -v "$PWD/vol-postgres":/from -v autobrain_postgres-data:/to \
    alpine sh -c 'cp -a /from/. /to/'
  # or pg_dump:
  docker compose -f docker-compose.prod.yml up -d postgres
  docker compose -f docker-compose.prod.yml exec -T postgres \
    pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < autobrain.dump
  docker compose -f docker-compose.prod.yml up -d
  ```

## Step 4 — Switch traffic

1. **DNS:** the site is fronted by Cloudflare. Change the `A` record for the
   public hostname from the old host IP to the new host IP. Keep it proxied
   (orange-cloud) so TLS/Cloudflare settings don't change.
2. **Reverse proxy:** if using Nginx Proxy Manager, point the proxy host at the
   stack's frontend nginx port on the new host.
3. **Stripe:** webhooks + checkout redirects use the public hostname, so no
   Stripe changes unless the hostname changed.

## Step 5 — Verify

| Check | Command / where |
|-------|-----------------|
| All services up | `docker compose -f docker-compose.prod.yml ps` |
| API healthy | `curl -fsS https://host/api/v1/../health` (or `/health`) |
| Login works | Log in with an existing account and with the admin account |
| Data present | A vehicle with photos, services, fuel history renders correctly |
| AI works | Run one AI diagnostic — confirm `model` is `9router` (router reachable) |
| Billing works | License screen shows current subscription; no re-payment needed |
| Background jobs | Watch logs for the daily backup and notification beats |

## Rollback

Keep the old host running (don't delete its volumes) until the new host has
passed Step 5. To roll back, flip the DNS record back to the old host IP —
nothing else changes.

## Secrets checklist for `.env`

`SECRET_KEY` · `STRIPE_SECRET_KEY` · `STRIPE_WEBHOOK_SECRET` ·
`STRIPE_PRICE_ENTHUSIAST_MONTHLY/YEARLY` · `STRIPE_PRICE_GARAGE_MONTHLY/YEARLY` ·
`AI_ROUTER_URL` · `AI_ROUTER_API_KEY` · `AI_ROUTER_MODEL` · `SMTP_HOST/USERNAME/PASSWORD` ·
`MINIO_ACCESS_KEY/SECRET_KEY` · `ADMIN_API_KEY` · `REGO_LOOKUP_API_KEY`

Per-instance secret values are recorded in Outline (internal-only), never in
this repo.
