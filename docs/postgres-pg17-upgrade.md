# PostgreSQL pg16 → pg17 upgrade (AUT-1749)

Major-version bump of the datastore image from `pgvector/pgvector:pg16` to
`pgvector/pgvector:pg17`, pinned by immutable **manifest-list digest** so the
multi-arch build (amd64 + arm64) is identical across Demo, Default and Hosted
(Hosted is the arm64 Oracle VM; the dev box / EP6 is x64).

```
pgvector/pgvector:pg17@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f
```

This is a **PostgreSQL MAJOR bump**. The on-disk cluster format changes, so the
existing `postgres-data` volume from pg16 cannot be opened by pg17 — it must be
migrated via dump/restore (recommended) or `pg_upgrade`. **Do not swap the image
and restart without a migration window:** pg17 will either refuse to start or
silently `initdb` a fresh, empty cluster and the app will come up with no users.

> **Promotion order is MANDATORY (AUT-107, `docs/deployment-guide.md`):** run and
> verify the migration on **Demo → Default → Hosted**, in that order. Hosted is
> the final, binding tier. Do not start a tier until the previous one passes the
> Verification section below.

## Files changed (this PR)

- `docker-compose.yml` (dev) — postgres image → pg17 @ digest
- `docker-compose.prod.yml` (Default / Demo) — postgres image → pg17 @ digest
- `docker-compose.hosted.yml` (AutoBrain-Hosted, EP5) — postgres image → pg17 @ digest
- `.github/workflows/trivy-image-scan.yml` + `.trivyignore` — image CVE gate now
  pins and scans the pg17 image (replaces the floating pg16 reference).

## Pre-flight

- Pick a maintenance window per tier (coordinated with CTO for Hosted, EP5).
- Confirm a current backup exists. On Hosted use the admin backup
  (`/api/v1/admin/backup`) **and** a `pg_dump` (below) — the dump is what we
  actually restore from, so it is the source of truth for rollback.
- Note the live `postgres-data` volume name (Compose prefixes it, e.g.
  `autobrain_postgres-data` / `autobrain-hosted_postgres-data`). Find it with
  `docker volume ls | grep postgres-data` on the target host.

## Procedure (dump/restore — PRIMARY, deterministic)

Works unchanged for dev (`docker-compose.yml`), Default/Demo (`docker-compose.prod.yml`)
and Hosted (`docker-compose.hosted.yml`). Differences per tier are called out.

### 1. Dump the old (pg16) cluster

```bash
# Default/Demo/dev — password from .env / stack env
docker compose [-f docker-compose.prod.yml] exec -T postgres \
  pg_dumpall -U "$POSTGRES_USER" > autobrain-pg16.dump.sql

# Hosted — password is in the secret file (no password in env)
docker compose -f docker-compose.hosted.yml exec -T postgres sh -c \
  'PGPASSWORD="$(cat /run/secrets/postgres_password)" pg_dumpall -U "$POSTGRES_USER"' \
  > autobrain-pg16.dump.sql
```

`pg_dumpall` captures roles + the `vector` extension ownership so the restore is
self-contained. (Use `-Fc` for a smaller custom-format file if you prefer
`pg_restore`, but plain SQL is simplest to eyeball.)

Treat the dump as secrets — it contains every user row (PII + bcrypt hashes).

### 2. Stop postgres and quarantine the old volume

```bash
docker compose [-f docker-compose.<tier>.yml] stop postgres
# keep the data, just rename it so pg17 can't touch it
docker volume ls | grep postgres-data          # note the real name
docker volume create autobrain_postgres-data_old
docker run --rm -v <real_postgres_data_volume>:/from -v autobrain_postgres-data_old:/to \
  alpine sh -c 'cp -a /from/. /to/'
```

### 3. Bring up pg17 on a fresh volume

```bash
docker compose [-f docker-compose.<tier>.yml] up -d postgres
# pg_isready should go green; the container initdb's a new empty cluster
docker compose [-f docker-compose.<tier>.yml] exec postgres pg_isready -U "$POSTGRES_USER"
```

### 4. Restore

```bash
# Default/Demo/dev
docker compose [-f docker-compose.prod.yml] exec -T postgres psql -U "$POSTGRES_USER" \
  -f - < autobrain-pg16.dump.sql

# Hosted (password from secret file)
docker compose -f docker-compose.hosted.yml exec -T postgres sh -c \
  'PGPASSWORD="$(cat /run/secrets/postgres_password)" psql -U "$POSTGRES_USER" -f -' \
  < autobrain-pg16.dump.sql
```

### 5. Restart the rest of the stack

```bash
docker compose [-f docker-compose.<tier>.yml] up -d
# backend runs `alembic upgrade head` / `app.db.bootstrap` automatically
```

## Procedure (`pg_upgrade` — ALTERNATIVE, faster for large DBs)

Use only when the dump/restore window is too long. Requires both pg16 and pg17
binaries side by side; run from a temporary migration container that mounts both
volumes and the pgvector libs.

```bash
# old = quarantined pg16 volume, new = fresh pg17 data dir
docker run --rm --name pg17-upgrade \
  -v <real_postgres_data_volume>_old:/var/lib/postgresql/old-data \
  -v autobrain_postgres-data:/var/lib/postgresql/new-data \
  pgvector/pgvector:pg17@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f \
  sh -c '
    chown -R postgres:postgres /var/lib/postgresql/old-data /var/lib/postgresql/new-data
    su postgres -c "/usr/lib/postgresql/17/bin/initdb -D /var/lib/postgresql/new-data"
    su postgres -c "/usr/lib/postgresql/17/bin/pg_upgrade \
      --old-datadir /var/lib/postgresql/old-data \
      --new-datadir /var/lib/postgresql/new-data \
      --old-bindir  /usr/lib/postgresql/16/bin \
      --new-bindir  /usr/lib/postgresql/17/bin \
      --link"
  '
```

Caveats: `--link` rewrites the old data dir in place (keep a copy first); the
pg16 bindir must be present in the pg17 image (it is not by default) — if missing,
use dump/restore instead. The `vector` extension is pre-installed in the pg17
image, so no manual extension install is needed.

## Verification (every tier, before promoting)

| Check | Command |
|-------|---------|
| Postgres healthy | `docker compose ... exec postgres pg_isready -U "$POSTGRES_USER"` → `accepting connections` |
| Cluster is pg17 | `docker compose ... exec postgres psql -U "$POSTGRES_USER" -tAc "SHOW server_version;"` → `17.x` |
| `vector` extension present | `SELECT extversion FROM pg_extension WHERE extname='vector';` (non-empty) |
| Users migrated (PII intact) | `SELECT count(*) FROM users;` matches the pre-migration count |
| Embeddings intact | `SELECT count(*) FROM diagnostics WHERE embedding IS NOT NULL;` > 0 (and same as pre-upgrade) |
| App healthy | `curl -fsS https://<tier>.autobrainservice.app/health` → 200 + version |
| Key flow | log in as admin + a real user; open a vehicle with photos/services; run one AI diagnostic |

Record the `users` and `diagnostics` counts **before** the window and assert they
are unchanged after restore — that is the acceptance proof that PII data is intact.

## Rollback

The quarantined `<volume>_old` is the rollback. To revert a tier:

```bash
docker compose [-f docker-compose.<tier>.yml] stop postgres
docker volume rm autobrain_postgres-data
docker volume create autobrain_postgres-data
docker run --rm -v autobrain_postgres-data_old:/from -v autobrain_postgres-data:/to \
  alpine sh -c 'cp -a /from/. /to/'
# revert the image line in the compose file for that tier, then:
docker compose [-f docker-compose.<tier>.yml] up -d
```

Keep `<volume>_old` until Hosted has passed Verification end-to-end, then prune.

## Trivy gate

`.github/workflows/trivy-image-scan.yml` scans the pinned pg17 image (and the
backend/ai base images) for HIGH/CRITICAL CVEs on PR + weekly. `.trivyignore`
holds review-approved exceptions. The gate must be green before merge and the
image digest must stay pinned — bump it deliberately (verify release notes) when
pgvector ships a new pg17 build.
