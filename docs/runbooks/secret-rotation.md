# Secret Rotation Runbook

## Overview
Procedures for rotating secrets across all AutoBrain environments. All secrets follow the `*_FILE` pattern (AUT-1533) for file-based injection in production.

## Secret Categories

### 1. Core Application Secrets
| Secret | Env Var | File Var | Rotation Frequency |
|--------|---------|----------|-------------------|
| JWT Signing Key | `SECRET_KEY` | `SECRET_KEY_FILE` | 90 days |
| PostgreSQL Password | `POSTGRES_PASSWORD` | `POSTGRES_PASSWORD_FILE` | 90 days |
| Redis Password | `REDIS_PASSWORD` | `REDIS_PASSWORD_FILE` | 90 days |
| MinIO Access/Secret | `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | `MINIO_ACCESS_KEY_FILE` / `MINIO_SECRET_KEY_FILE` | 90 days |

### 2. External Service Secrets
| Secret | Env Var | File Var | Rotation Frequency |
|--------|---------|----------|-------------------|
| AI Router API Key | `AI_ROUTER_API_KEY` | `AI_ROUTER_API_KEY_FILE` | 90 days |
| AI Gateway API Key | `AI_GATEWAY_API_KEY` | `AI_GATEWAY_API_KEY_FILE` | 90 days |
| SMTP Password | `SMTP_PASSWORD` | `SMTP_PASSWORD_FILE` | 90 days |
| Stripe Keys | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | `*_FILE` | Per Stripe policy |
| Rego Lookup API Key | `REGO_LOOKUP_API_KEY` | `REGO_LOOKUP_API_KEY_FILE` | As needed |
| Fuel Price API Keys | `FUEL_NSW_API_KEY`, `FUEL_VIC_API_KEY`, `FUEL_QLD_API_KEY` | `*_FILE` | As needed |

### 3. Admin & Machine-to-Machine
| Secret | Env Var | File Var | Rotation Frequency |
|--------|---------|----------|-------------------|
| Admin Initial Password | `ADMIN_INITIAL_PASSWORD` | `ADMIN_INITIAL_PASSWORD_FILE` | On rotation |
| Admin API Key | `ADMIN_API_KEY` | `ADMIN_API_KEY_FILE` | 90 days |
| Demo Password | `DEMO_PASSWORD` | `DEMO_PASSWORD_FILE` | As needed |
| Dongle Server API Key | `DONGLE_SERVER_API_KEY` | `DONGLE_SERVER_API_KEY_FILE` | 90 days |

### 4. Off-site Backup
| Secret | Env Var | File Var | Rotation Frequency |
|--------|---------|----------|-------------------|
| Backup GUI Key | `BACKUP_OFFSITE_GUI_KEY` | `BACKUP_OFFSITE_GUI_KEY_FILE` | 90 days |
| Backup Ingest Key | `BACKUP_OFFSITE_INGEST_KEY` | `BACKUP_OFFSITE_INGEST_KEY_FILE` | 90 days |

## Rotation Procedures

### Generate New Secret
```bash
# For passwords/keys (64-char URL-safe)
openssl rand -base64 48 | tr -d '\n' > /path/to/secret_file

# For JWT keys (URL-safe, 64 bytes)
python -c "import secrets; print(secrets.token_urlsafe(64))" > /path/to/secret_file

# For API keys (shorter, alphanumeric)
openssl rand -hex 32 | tr -d '\n' > /path/to/secret_file
```

### Rotate SECRET_KEY (JWT Signing)
**Impact:** Invalidates ALL existing sessions. Plan for maintenance window.

1. Generate new key: `python -c "import secrets; print(secrets.token_urlsafe(64))" > new_secret_key`
2. Update secret file on all environments (dev, demo, default, hosted)
3. Restart backend containers to pick up new key
4. All users must re-login
5. Update Paperclip secrets: `paperclip secrets set SECRET_KEY_FILE < new_secret_key`

### Rotate Database Passwords (PostgreSQL/Redis/MinIO)
**Impact:** Requires coordinated restart of all services.

1. Generate new passwords for each service
2. Update secret files on all environments
3. Update Portainer stack env vars (or Docker secrets in prod)
4. Restart services in order: postgres → redis → minio → backend → ai → frontend
5. Verify each service health

### Rotate AI Gateway API Key
1. Generate new key: `openssl rand -hex 32 > new_ai_gateway_key`
2. Update `AI_GATEWAY_API_KEY_FILE` on backend and AI gateway
3. Restart backend and AI gateway containers
4. Verify AI gateway `/health` shows `router_enabled: true`

### Rotate Admin Password
See [Deployment Guide](../Deployment-and-Infrastructure/deployment-guide.md#admin-password-rotation-aut-5135) for the `admin_reset` CLI procedure.

### Rotate Demo Password
1. Generate new password
2. Update Paperclip secret `demo/demo-account-password`
3. Update `DEMO_PASSWORD_FILE` on demo stack
4. Restart demo backend container
5. Verify demo login works

## Environment-Specific Procedures

### Development (docker-compose.yml)
```bash
# Edit .env or secret files in ./secrets/
# Restart containers
docker compose restart backend ai
```

### Demo / Default (Portainer EP2)
1. Update secret files in `/data/autobrain/secrets/` (or `/data/autobrain-demo/secrets/`)
2. Portainer → Stacks → Update → `pullImage: true` (or just redeploy)
3. Verify health checks pass

### Hosted (Portainer EP5, Oracle Cloud)
1. Update secret files in `/data/autobrain/secrets/`
2. Portainer → Stacks → `autobrain-hosted` → Update → `pullImage: true`
3. Run `scripts/sync-compose-to-portainer.py --verify-only --stack autobrain-hosted --endpoint 5 --file docker-compose.hosted.yml`
4. Run post-deploy smoke test

## Verification Checklist
- [ ] All secret files updated with new values
- [ ] All containers restarted and healthy
- [ ] Backend `/health` returns 200
- [ ] AI gateway `/health` returns 200 with `router_enabled: true`
- [ ] Admin login works (if SECRET_KEY rotated)
- [ ] Demo login works (if demo password rotated)
- [ ] API endpoints respond correctly
- [ ] Celery tasks processing (check logs)

## Emergency Rollback
If rotation causes issues:
1. Restore previous secret files from backup
2. Restart affected containers
3. If SECRET_KEY rotated and causing issues, revert and all sessions restored
4. Document incident and root cause

## Related Docs
- [Deployment Guide](../Deployment-and-Infrastructure/deployment-guide.md#admin-password-rotation-aut-5135)
- [Security Policy](../Security/security.md)
- [Backup & Restore Runbook](./backup-restore.md)
