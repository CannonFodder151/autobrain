# Backup Strategy

## What to back up

1. **PostgreSQL** — all app data.
2. **MinIO bucket** — receipts, photos, uploads.
3. **`.env`** — environment configuration (store separately, encrypted).

## autobrain-backup service (recommended)

### Portainer-Host (Endpoint 2 — On-Prem)

The `autobrain-backup` service runs on the Portainer-Host (port 8080) and
provides hourly/daily/weekly backups:

- **`autobrain-backup`** — web GUI, restore feature, health/stats, email alerts
  on failure/corruption, config on the docker host (`/srv/autobrain-backup/config`).
- **`backup-agent`** — pulls backups hourly from the instance admin API
  (`/api/v1/admin-api/backup`) with the per-instance admin API key, combines to
  hourly/daily/weekly, stores under `/srv/autobrain-backup/agent-data`, retention 30.

### AutoBrain-Hosted / EP5 (Endpoint 5 — Oracle Cloud VM <HOSTED_VM_IP>)

The hosted stack (`autobrain-hosted`, Portainer stack #122) includes its own
backup infrastructure:

- **`autobrain-backup`** — web GUI (port 8080, bound to `127.0.0.1`), restore
  feature, health/stats. Config persisted in bind mount
  `/data/autobrain-backup/config` (on the Oracle VM). Image:
  `ghcr.io/cannonfodder151/autobrain-backup:hosted@sha256:e76fac3c69ce5d6e2f670cbe9d41f72fec235d6769bf9f046faa71c9c06b4880`

**AUT-3827 (off-site backup consolidation):** The standalone `backup-agent`
container was **removed**. Its job (hourly snapshot push to `autobrain-backup`)
now runs as a Celery beat task **inside the `backend` container**
(`app.workers.tasks.backup_offsite_hourly`, at `:00` each hour). The backend
pushes a snapshot to `autobrain-backup` at `http://autobrain-backup:8080`
using `BACKUP_OFFSITE_*` env vars (injected via Portainer stack env and
secret files). The hosted stack drops from 8 to 7 long-running containers.

**Volumes (Oracle VM, `/data` — see AUT-1853):**

| Volume | Path | Purpose |
|--------|------|---------|
| `autobrain-backup-data` | `/data/autobrain-backup/data` | Backup artifacts served by `autobrain-backup` GUI |
| `autobrain-backup-config` | `/data/autobrain-backup/config` | `autobrain-backup` configuration (schedules, retention, notifications) |

**Secret provisioning (AUT-1533 / AUT-1853):** The hosted stack's
`ADMIN_API_KEY` and the off-site backup keys (`BACKUP_OFFSITE_GUI_KEY_FILE`,
`BACKUP_OFFSITE_INGEST_KEY_FILE`) are seeded as secret files
(`/run/secrets/...`) via `scripts/seed-secrets.sh` **before** deploying the
stack. The secret file pattern ensures keys never appear in `docker inspect`.
See `scripts/seed-secrets.sh` and `docs/security.md` ("Secret-file pattern & broker auth").

**Network:** Services run on the `autobrain-hosted` stack's default
Docker network (`172.18.0.0/16`). The backend reaches the GUI at
`http://autobrain-backup:8080`.

**Access:** The `autobrain-backup` GUI is bound to `127.0.0.1:8080` on the
Oracle VM. External access is via the host nginx-proxy-manager (if configured)
or SSH tunnel; it is not directly exposed to the internet.

## Admin JSON backup (instant, in-app)

`GET /admin/backup` (admin-authenticated) downloads a full JSON snapshot of the
database. `POST /admin/restore` wipes and restores from a backup file. The daily
Celery beat task also writes a JSON backup to MinIO (`backups/`) with retention
of `BACKUP_RETENTION_DAYS` (default 14).

Recommended cron (on the server, legacy):

```cron
30 2 * * * /data/autobrain/scripts/backup.sh /backups && \
  find /backups -name "autobrain-backup-*" -mtime +14 -delete
```

> **Note (AUT-1853):** `/data/autobrain/` replaces `/opt/autobrain/` on the
> Oracle VM because the snap dockerd mounts `/opt` from a read-only core24
> squashfs, masking the host `/opt`. `/data` is on the daemon-visible rootfs
> and is never masked.

## Full-fidelity backup (volume copy / pg_dump)

For a migration or full data fidelity (DB + files):

```bash
docker run --rm -v autobrain_postgres-data:/from -v "$PWD/vol-postgres":/to \
  alpine sh -c 'cp -a /from/. /to/'
docker run --rm -v autobrain_minio-data:/from -v "$PWD/vol-minio":/to \
  alpine sh -c 'cp -a /from/. /to/'
```

Or a clean Postgres dump:

```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" > autobrain.dump
```

## Restore

```bash
# Database (pg_dump)
docker compose -f docker-compose.prod.yml up -d postgres
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < autobrain.dump

# MinIO (AUT-1242-C2: bucket init is now in the minio entrypoint; mc ships in the minio image)
docker compose -f docker-compose.prod.yml exec -T minio sh -c \
  "mc alias set local http://localhost:9000 ${MINIO_ACCESS_KEY} ${MINIO_SECRET_KEY} && mc mirror /local-restore local/autobrain-assets"
```

JSON backup restore is done in-app: admin → Backup & restore → upload → confirm.

## Recovery objectives

- RPO: up to 24h (daily backup), down to hourly via the backup agent.
- RTO: ~15–30 min (restore + `docker compose up`).

## Notes

- Schedule valuation snapshots etc. are re-generated by Celery beat on restore.
- Keep a backup of the first working deploy so you can roll the whole stack back.
- Test the restore path at least once per quarter on a non-production instance.
