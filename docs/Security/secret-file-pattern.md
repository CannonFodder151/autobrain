# Secret File Pattern (AUT-1533)

AutoBrain uses a **secret-file pattern** for all sensitive configuration values. This document describes the pattern, how to use it, and how to seed secrets on each environment.

## Why Secret Files?

- Secrets never appear in `docker inspect` or process environment dumps
- No risk of leaking credentials via `docker-compose` interpolation or logging
- Works with Portainer's secret management and Docker's native `*_FILE` support
- Consistent across all services (PostgreSQL, Redis, MinIO, backend, etc.)

## Pattern

For every secret value, define **two** environment variables:

| Plain env var | Secret-file env var | Purpose |
|---------------|---------------------|---------|
| `POSTGRES_PASSWORD` | `POSTGRES_PASSWORD_FILE` | Database password |
| `REDIS_PASSWORD` | `REDIS_PASSWORD_FILE` | Redis password |
| `MINIO_ROOT_PASSWORD` | `MINIO_SECRET_KEY_FILE` | MinIO secret key |
| `SECRET_KEY` | `SECRET_KEY_FILE` | Backend JWT signing key |

**Only the `_FILE` variant is used at runtime.** The plain variant exists only as a documentation placeholder in `.env.example` and must never be set in production.

## Directory Structure

All secret files are bind-mounted from a single host directory into `/run/secrets` inside every container:

```
Host:          /data/autobrain/secrets/
Container:     /run/secrets/
```

Each file contains exactly one secret value (no trailing newline preferred):

```
/data/autobrain/secrets/postgres_password      → "supersecret123"
/data/autobrain/secrets/redis_password         → "redissecret456"
/data/autobrain/secrets/backend_secret_key     → "jwt-signing-key-abc"
```

## Docker Compose Usage

```yaml
x-secrets: &secrets
  volumes:
    - type: bind
      source: ${SECRETS_DIR:-/data/autobrain/secrets}
      target: /run/secrets
      read_only: true

services:
  backend:
    <<: *secrets
    environment:
      SECRET_KEY_FILE: /run/secrets/backend_secret_key
      # DO NOT set SECRET_KEY
```

## Native `*_FILE` Support

These images support `*_FILE` env vars natively (no entrypoint wrapper needed):

| Image | Supported `*_FILE` vars |
|-------|------------------------|
| `postgres` | `POSTGRES_PASSWORD_FILE` |
| `redis` | (via entrypoint wrapper) |
| `minio/minio` | `MINIO_ROOT_PASSWORD_FILE` |

For images without native support (backend, dongle-server, etc.), the `docker/lib-load-secrets.sh` entrypoint wrapper reads `_FILE` vars and exports the plain variants into the process environment before the application starts.

## lib-load-secrets.sh

Located at `docker/lib-load-secrets.sh`. Reads all `*_FILE` environment variables, loads the file content, and exports the plain variable:

```bash
# Example: SECRET_KEY_FILE=/run/secrets/backend_secret_key
# Becomes: SECRET_KEY="actual-secret-value"
```

Usage in Dockerfile:

```dockerfile
COPY docker/lib-load-secrets.sh /usr/local/bin/
ENTRYPOINT ["/usr/local/bin/lib-load-secrets.sh"]
CMD ["your", "application", "command"]
```

## Seeding Secrets

Use `scripts/seed-secrets.sh` to provision the secret directory on a fresh host:

```bash
# On the target host (as root or with sudo):
sudo ./scripts/seed-secrets.sh
```

The script:
1. Creates `/data/autobrain/secrets` with `root:1000` ownership and `0750` perms
2. Generates or prompts for each required secret
3. Writes each secret to its own file with `0640` perms
4. Skips existing files (idempotent)

### Required Secret Files

| File | Description | Generated? |
|------|-------------|------------|
| `postgres_password` | PostgreSQL superuser password | Yes (random) |
| `redis_password` | Redis `requirepass` value | Yes (random) |
| `minio_access_key` | MinIO root access key | Yes (minioadmin) |
| `minio_secret_key` | MinIO root secret key | Yes (random) |
| `backend_secret_key` | JWT signing key (HS256) | Yes (random 64-char) |
| `admin_initial_password` | First admin user password | Yes (random) |
| `admin_api_key` | Admin API bearer token | Yes (random) |
| `ai_router_api_key` | 9Router API key | No (from 9Router admin) |
| `ai_gateway_api_key` | AI gateway internal key | Yes (random) |
| `fuel_nsw_api_key` | NSW FuelCheck API key | No (from Transport NSW) |
| `fuel_nsw_api_secret` | NSW FuelCheck API secret | No (from Transport NSW) |
| `fuel_vic_api_key` | VIC Servo Saver API key | No (from partner) |
| `fuel_vic_api_secret` | VIC Servo Saver API secret | No (from partner) |
| `fuel_qld_api_key` | QLD FuelPricesQLD subscriber token | No (from provider) |
| `fuel_sa_api_key` | SA SAFPIS API key | No (from provider) |
| `rego_lookup_api_key` | Rego lookup API key | No (from provider) |
| `dongle_server_api_key` | Dongle-server ↔ backend shared key | Yes (random) |
| `dongle_web_basic_password` | Dongle-server GUI basic auth | Yes (random) |
| `hub_hosted_registration_key` | Federation hub hosted registration | Yes (random) |
| `backup_offsite_gui_key` | Backup GUI auth key | Yes (random) |
| `backup_offsite_ingest_key` | Backup ingest API key | Yes (random) |
| `smtp_username` | SMTP2GO username | No (from provider) |
| `smtp_password` | SMTP2GO password | No (from provider) |
| `stripe_secret_key` | Stripe secret key | No (from Stripe dashboard) |
| `stripe_webhook_secret` | Stripe webhook signing secret | No (from Stripe dashboard) |
| `iap_google_service_account_json` | Google Play service account JSON | No (from GCP) |
| `iap_apple_private_key` | Apple App Store Connect private key | No (from App Store Connect) |

## Adding a New Secret

1. Add the secret file to `scripts/seed-secrets.sh` (in the `SECRETS` array)
2. Update the service's `docker-compose.yml` to mount `*_FILE` env var
3. Update the service code to read from the `_FILE` env var (or use `lib-load-secrets.sh`)
4. Run `seed-secrets.sh` on target hosts
5. Redeploy the stack

## Host-Specific Notes

### Oracle VM (EP5, hosted)
- Snap dockerd on Ubuntu Core 24 mounts `/opt` from a read-only squashfs
- **Use `/data/autobrain/secrets` NOT `/opt/autobrain/secrets`** (AUT-1853)
- The `SECRETS_DIR` env var defaults to `/data/autobrain/secrets`

### Dev Box / Demo / Default (EP2)
- Standard Docker, `/opt/autobrain/secrets` works
- `SECRETS_DIR` can be overridden per environment

## Security Checklist

- [ ] Secret directory is `0750` (`root:1000`)
- [ ] Secret files are `0640` (`root:1000`)
- [ ] No secret appears in `docker inspect <container> | grep -i secret`
- [ ] No secret appears in `docker exec <container> env | grep -i secret`
- [ ] All secrets seeded before first deploy
- [ ] `seed-secrets.sh` is idempotent (safe to re-run)
- [ ] Backup off-site keys rotate on schedule (TBD)

## Troubleshooting

**Container fails with "permission denied" on secret file:**
- Check `/data/autobrain/secrets` ownership is `root:1000`
- Container user must be in group `1000` (Docker default for bind mounts)

**App reads empty secret:**
- File may have trailing newline → use `cat file | tr -d '\n'` when generating
- Verify `_FILE` env var points to correct path

**Secret not picked up after rotation:**
- Restart the container (bind mounts are not hot-reloaded)
- Or use Docker secrets with `docker service update --secret-rm/--secret-add` (Swarm mode only)