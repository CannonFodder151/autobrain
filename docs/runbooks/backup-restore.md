# Backup & Restore Runbook

## Overview
AutoBrain supports two backup systems:
1. **Admin Backup** — Daily full-DB JSON snapshots to MinIO (configurable retention)
2. **Off-site Backup** — Hourly snapshots pushed to a separate backup instance

## Admin Backup (MinIO)

### Enable/Configure
```bash
# In .env or stack env
BACKUP_ENABLED=true
BACKUP_RETENTION_DAYS=14
```

### Manual Backup (via Admin UI)
1. Go to Admin → Backup & Restore
2. Click "Create Backup"
3. Wait for completion (shows in backup list)

### Manual Backup (via CLI)
```bash
# Inside backend container
docker compose exec backend python -m app.services.backup create_backup
```

### List Backups
```bash
# Inside backend container
docker compose exec backend python -m app.services.backup list_backups
```

### Restore from Backup
```bash
# Inside backend container
docker compose exec backend python -m app.services.backup restore_backup <backup-id>
```

⚠️ **Warning**: Restore wipes current data. Verify backup ID first.

### Prune Old Backups
```bash
# Inside backend container (runs daily via Celery Beat)
docker compose exec backend python -m app.services.backup prune_backups
```

## Off-site Backup (Backup Instance)

### Enable/Configure
```bash
# In .env or stack env (hosted)
BACKUP_OFFSITE_URL=http://backup:8080
BACKUP_OFFSITE_INSTANCE=hosted
BACKUP_OFFSITE_GUI_KEY=<from secrets>
BACKUP_OFFSITE_INGEST_KEY=<from secrets>
BACKUP_OFFSITE_HOST_ALLOWLIST='["backup"]'
```

### Manual Trigger
```bash
# Inside backend container (Celery task)
docker compose exec backend python -c "
from app.celery_app import celery
celery.send_task('backup_offsite_hourly')
"
```

### Verify Off-site Backup
```bash
# Check backup instance GUI at BACKUP_OFFSITE_URL
# Or check Celery logs for backup_offsite_hourly task
docker compose logs backend | grep backup_offsite
```

## Disaster Recovery

### Full Restore Procedure
1. **Stop services** (prevent writes during restore):
   ```bash
   docker compose stop backend ai celery worker beat
   ```

2. **Restore database** from backup:
   ```bash
   # Option A: Admin backup (JSON)
   docker compose exec backend python -m app.services.backup restore_backup <backup-id>

   # Option B: pg_dump/pg_restore (if you have SQL dump)
   docker compose exec -T postgres pg_restore -U postgres -d autobrain < dump.sql
   ```

3. **Restore MinIO objects** (if needed):
   ```bash
   # Using mc (MinIO client)
   mc mirror <source> minio/autobrain-assets
   ```

4. **Start services**:
   ```bash
   docker compose up -d backend ai celery worker beat
   ```

5. **Verify**:
   ```bash
   curl https://<domain>/health
   ./scripts/post-deploy-smoke.sh https://<domain>
   ```

### Point-in-time Recovery (PostgreSQL WAL)
Not currently configured. For PITR, set up:
- `wal_level = replica`
- `archive_mode = on`
- WAL archiving to MinIO/S3

## Backup Verification Checklist
- [ ] Daily admin backup runs (check Celery Beat logs)
- [ ] Backup appears in MinIO `backups/` bucket
- [ ] Backup file is valid JSON (`jq . < backup.json`)
- [ ] Off-site backup syncs to backup instance (hourly)
- [ ] Retention pruning works (old backups deleted)
- [ ] Test restore performed quarterly

## Related Docs
- [Deployment Guide](../Deployment-and-Infrastructure/deployment-guide.md#admin-password-rotation-aut-5135)
- [Backup Strategy](../Deployment-and-Infrastructure/backup-strategy.md)