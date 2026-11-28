# Database Migration Runbook

## Overview
Procedures for running, verifying, and troubleshooting Alembic database migrations in AutoBrain.

## Prerequisites
- Access to the target environment (dev, demo, default, hosted)
- Docker Compose or Portainer access
- Understanding of the migration history (`alembic history`)

## Running Migrations

### Development (Local)
```bash
# Generate a new migration
docker compose exec backend alembic revision --autogenerate -m "description"

# Apply migrations
docker compose exec backend alembic upgrade head

# Check current revision
docker compose exec backend alembic current
```

### Demo / Default (Portainer EP2)
Migrations run automatically on backend container startup via `python -m app.db.bootstrap`.
To force a migration run:
```bash
# Via Portainer exec on backend container
python -m app.db.bootstrap
# Or explicitly:
alembic upgrade head
```

### Hosted (Portainer EP5, Oracle Cloud)
Migrations run automatically on backend container startup. The hosted stack uses the
inline compose (stack 122) which is updated via `sync-compose-to-portainer.py`.

To verify migrations applied:
```bash
# Check backend logs for migration output
docker logs <backend-container> | grep -E "alembic|upgrade|migration"

# Or via Portainer exec
alembic current
alembic history
```

## Common Issues

### Multiple Head Revisions
**Symptom:** `alembic upgrade head` fails with "Multiple head revisions present"

**Resolution:**
```bash
# Check heads
alembic heads

# Merge heads (create a merge revision)
alembic merge heads -m "merge heads"

# Then upgrade
alembic upgrade head
```

### Migration Fails with `create_all` Fallback
**Symptom:** Backend logs show `alembic_failed_falling_back_to_create_all`

**Resolution:**
1. Stop the deploy immediately
2. Fix the broken migration locally
3. Test with `docker compose -f docker-compose.hosted.yml run --rm backend alembic upgrade head`
4. Re-deploy

**Never** paper over with `create_all` — it only creates missing tables, not columns or indexes.

### Missing Columns After `alembic stamp`
**Symptom:** Runtime `UndefinedColumnError` after using `alembic stamp` to skip a migration

**Resolution:**
1. Verify columns exist: `psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT column_name FROM information_schema.columns WHERE table_name='<target_table>'"`
2. If missing, create a proper migration or manually `ALTER TABLE`
3. Only then `alembic stamp <revision>` if schema is verified correct

### Stale `create_all`-Hybrid Databases
**Background:** Databases bootstrapped via `create_all` fallback (pre-v0.3.43) have tables Alembic never saw.

**Resolution (v0.3.43+):** Social migrations are now linear and idempotent:
- `n4p5q6r7s8t9` reparented onto `a5b6c7d8e9f0`
- Every DDL op guarded for already-present tables/columns
- `alembic upgrade head` now succeeds on these DBs

## Verification Checklist
- [ ] `alembic current` shows expected revision
- [ ] `alembic history` shows linear chain to head
- [ ] No `alembic_failed_falling_back_to_create_all` in logs
- [ ] Backend `/health` returns 200
- [ ] Celery worker logs show `alembic_migrations_applied` on next boot

## Related Docs
- [Deployment Guide](../Deployment-and-Infrastructure/deployment-guide.md#migrations)
- [Alembic Stamp Checklist](../Deployment-and-Infrastructure/deployment-guide.md#alembic-stamp-checklist-aut-2065)
- [PostgreSQL 17 Upgrade](../Engineering/postgresql-17-upgrade.md)
