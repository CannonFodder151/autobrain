# Secret-File Pattern (AUT-1533)

## Overview

The secret-file pattern (`*_FILE` suffix) is the standard mechanism for injecting secrets into AutoBrain containers. It ensures secrets never appear in `docker inspect`, environment variable dumps, or CI logs.

## How It Works

### 1. Secret Storage

Secrets are stored as plain-text files in a host directory:
```
/data/autobrain/secrets/
├── postgres_password
├── redis_password
├── minio_access_key
├── minio_secret_key
├── backend_secret_key
├── ai_router_api_key
├── smtp_username
├── smtp_password
└── ... (one file per secret)
```

**Permissions:** `root:1000`, `0640` (readable by container user, not world-readable).

### 2. Bind Mount in docker-compose

Each service that needs secrets declares a bind mount:

```yaml
x-secrets: &secrets
  volumes:
    - type: bind
      source: ${SECRETS_DIR:-/data/autobrain/secrets}
      target: /run/secrets
      read_only: true
```

Services include `<<: *secrets` to inherit the mount.

### 3. Runtime Loading via `lib-load-secrets.sh`

At container start, `docker/lib-load-secrets.sh` runs as the entrypoint wrapper. It:
1. Reads each file in `/run/secrets/`
2. Strips the `_FILE` suffix from the filename
3. Exports the content as an environment variable

Example:
- File: `/run/secrets/postgres_password` → Env: `POSTGRES_PASSWORD=actualpassword`
- File: `/run/secrets/redis_password` → Env: `REDIS_PASSWORD=actualpassword`

### 4. Configuration References

In docker-compose, services reference the secret file path:

```yaml
environment:
  POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
  REDIS_PASSWORD_FILE: /run/secrets/redis_password
```

The application code (via Pydantic Settings) reads `*_FILE` vars and loads the content.

## Provisioning: `scripts/seed-secrets.sh`

Before deploying a stack, run the seed script to create secret files:

```bash
./scripts/seed-secrets.sh
```

This script:
- Reads secret values from Paperclip secret store
- Writes them to `/data/autobrain/secrets/` with correct permissions
- Creates parent directories if needed

**Never commit secret files to git.** They are gitignored.

## Host-Specific Notes

### Oracle VM (Hosted, EP5)

The snap dockerd on the Oracle VM mounts `/opt` from a read-only core24 squashfs and masks the host `/opt`. A bind mount on `/opt/autobrain/secrets` fails with "read-only file system".

**Solution:** Use `/data/autobrain/secrets` instead (AUT-1853). `/data` is on the daemon-visible rootfs and is never masked.

```yaml
# In docker-compose.hosted.yml
x-secrets: &secrets
  volumes:
    - type: bind
      source: ${SECRETS_DIR:-/data/autobrain/secrets}
      target: /run/secrets
      read_only: true
```

### Dev Box / Default / Demo (EP2, EP6)

Standard `/opt/autobrain/secrets` or `/data/autobrain/secrets` works. The `SECRETS_DIR` env var can override.

## Supported Images

Images with native `*_FILE` support (no `lib-load-secrets.sh` needed):
- `postgres` — `POSTGRES_PASSWORD_FILE`
- `redis` — via entrypoint wrapper
- `minio/minio` — `MINIO_ROOT_USER_FILE`, `MINIO_ROOT_PASSWORD_FILE`

For other images, `lib-load-secrets.sh` handles the conversion.

## Security Properties

| Property | Guarantee |
|----------|-----------|
| No secrets in `docker inspect` | Secrets are in bind-mounted files, not env vars |
| No secrets in CI logs | Seed script runs on host, not in CI |
| No secrets in image layers | Secrets mounted at runtime only |
| Least privilege | Files `0640`, owned by `root:1000` |
| Audit trail | Paperclip secret store tracks access |

## Migration from Plain Env Vars

When migrating a service to the secret-file pattern:

1. Add the secret to Paperclip secret store
2. Add `*_FILE` entry to docker-compose environment
3. Add bind mount via `<<: *secrets`
4. Update application code to read `*_FILE` via Pydantic Settings
5. Run `seed-secrets.sh` before deploy
6. Remove plain env var from docker-compose

## Troubleshooting

### "Permission denied" on secret file
- Check file permissions: `ls -la /data/autobrain/secrets/`
- Should be `root:1000` and `0640`
- Fix: `chown root:1000 /data/autobrain/secrets/* && chmod 0640 /data/autobrain/secrets/*`

### "Read-only file system" on Oracle VM
- Ensure `SECRETS_DIR` points to `/data/autobrain/secrets`, not `/opt/autobrain/secrets`
- Verify `/data` is writable: `touch /data/test && rm /data/test`

### Secret not loaded into container
- Verify bind mount in `docker inspect <container>` → `Mounts`
- Check `/run/secrets/` inside container: `docker exec <container> ls /run/secrets/`
- Verify `lib-load-secrets.sh` ran: `docker exec <container> env | grep -E "_PASSWORD|_KEY|_SECRET"`

## Related Issues

- AUT-1533: Original remediation for stack-config audit findings
- AUT-1853: Oracle VM `/opt` read-only fix
- AUT-3153: Container consolidation (worker merge)
- AUT-3827: Backup offsite push (backend Celery beat)

## See Also

- `docs/Security/security.md` — Security policy index
- `docs/Deployment-and-Infrastructure/deployment-guide.md` — Deployment procedures
- `scripts/seed-secrets.sh` — Provisioning script
- `docker/lib-load-secrets.sh` — Runtime loader
