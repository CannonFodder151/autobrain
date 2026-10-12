# Secret-File Pattern (AUT-1533)

## Overview

AutoBrain uses a **secret-file pattern** to keep credentials out of environment
variables, `docker inspect`, and compose files. Secrets are bind-mounted from
a host directory into containers at `/run/secrets/` and loaded into process
environment at container start by `docker/lib-load-secrets.sh`.

## Host Layout

```
/data/autobrain/secrets/          # default SECRETS_DIR (host path)
├── postgres_password             # mode 0640, root:1000
├── redis_password
├── minio_access_key
├── minio_secret_key
├── backend_secret_key
├── ai_router_api_key
├── ai_gateway_api_key
├── admin_api_key
├── admin_initial_password
├── smtp_username
├── smtp_password
├── stripe_secret_key
├── stripe_webhook_secret
├── dongle_server_api_key
├── dongle_web_basic_password
├── fuel_nsw_api_key
├── fuel_nsw_api_secret
├── fuel_vic_api_key
├── fuel_vic_api_secret
├── fuel_qld_api_key
├── fuel_sa_api_key
├── rego_lookup_api_key
├── backup_offsite_gui_key
├── backup_offsite_ingest_key
├── hub_hosted_registration_key
├── iap_google_service_account_json
├── iap_apple_private_key
└── ...
```

## Container Wiring

### 1. Compose volume bind

```yaml
x-secrets: &secrets
  volumes:
    - type: bind
      source: ${SECRETS_DIR:-/data/autobrain/secrets}
      target: /run/secrets
      read_only: true
```

### 2. `*_FILE` environment variables

Each secret is referenced by a `*_FILE` env var pointing at the in-container
path:

```yaml
environment:
  POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
  MINIO_ACCESS_KEY_FILE: /run/secrets/minio_access_key
  MINIO_SECRET_KEY_FILE: /run/secrets/minio_secret_key
```

### 3. Loader script

`docker/lib-load-secrets.sh` runs at container start (before the app), reads
each `*_FILE` var, and `export`s the file's contents under the base name:

```sh
# Example: POSTGRES_PASSWORD_FILE -> POSTGRES_PASSWORD
for var in $(env | grep '_FILE=' | cut -d= -f1); do
  base="${var%_FILE}"
  file="${!var}"
  if [ -f "$file" ]; then
    export "$base=$(cat "$file")"
  fi
done
```

## Supported `*_FILE` Variables

| Variable | Container | App |
|----------|-----------|-----|
| `POSTGRES_PASSWORD_FILE` | postgres, backend | SQLAlchemy |
| `MINIO_ACCESS_KEY_FILE` | minio | MinIO SDK |
| `MINIO_SECRET_KEY_FILE` | minio | MinIO SDK |
| `REDIS_PASSWORD_FILE` | redis | Celery broker |
| `SECRET_KEY_FILE` | backend | FastAPI sessions |
| `AI_ROUTER_API_KEY_FILE` | backend, ai | 9Router client |
| `AI_GATEWAY_API_KEY_FILE` | backend | AI gateway auth |
| `ADMIN_API_KEY_FILE` | backend | Admin API |
| `ADMIN_INITIAL_PASSWORD_FILE` | backend | Bootstrap |
| `SMTP_USERNAME_FILE` | backend | Email |
| `SMTP_PASSWORD_FILE` | backend | Email |
| `STRIPE_SECRET_KEY_FILE` | backend | Stripe |
| `STRIPE_WEBHOOK_SECRET_FILE` | backend | Stripe webhooks |
| `DONGLE_SERVER_API_KEY_FILE` | backend | Dongle server |
| `DONGLE_WEB_BASIC_PASSWORD_FILE` | backend | Dongle web UI |
| `FUEL_NSW_API_KEY_FILE` | backend | NSW Fuel API |
| `FUEL_NSW_API_SECRET_FILE` | backend | NSW Fuel API |
| `FUEL_VIC_API_KEY_FILE` | backend | VIC Servo Saver |
| `FUEL_VIC_API_SECRET_FILE` | backend | VIC Servo Saver |
| `FUEL_QLD_API_KEY_FILE` | backend | QLD DirectAPI |
| `FUEL_SA_API_KEY_FILE` | backend | SA SAFPIS |
| `REGO_LOOKUP_API_KEY_FILE` | backend | Rego lookup |
| `BACKUP_OFFSITE_GUI_KEY_FILE` | backend | Backup GUI |
| `BACKUP_OFFSITE_INGEST_KEY_FILE` | backend | Backup ingest |
| `HUB_HOSTED_REGISTRATION_KEY_FILE` | backend | Federation hub |
| `IAP_GOOGLE_SERVICE_ACCOUNT_JSON_FILE` | backend | Google IAP |
| `IAP_APPLE_PRIVATE_KEY_FILE` | backend | Apple IAP |

## Seeding Secrets

Run `scripts/seed-secrets.sh` on the host before deploying:

```bash
#!/bin/bash
# scripts/seed-secrets.sh
SECRETS_DIR="${SECRETS_DIR:-/data/autobrain/secrets}"
mkdir -p "$SECRETS_DIR"
chmod 750 "$SECRETS_DIR"

# Generate or copy secrets
echo -n "generate-me" > "$SECRETS_DIR/postgres_password"
chmod 640 "$SECRETS_DIR/postgres_password"
# ... repeat for each secret
```

## Security Properties

1. **Not in `docker inspect`** — secrets are file binds, not env vars.
2. **Not in compose files** — only `*_FILE` paths appear, never values.
3. **Read-only** — the bind is `read_only: true`; containers cannot modify.
4. **Not in shell history** — loader reads files, not command-line args.
5. **Not in process env of other containers** — each container only sees its own binds.

## Rotation

1. Write new secret file on host.
2. `docker compose up -d` (recreate containers).
3. Verify app picks up new value.
4. Old secret is overwritten in place.

## Related

- AUT-1533: original implementation
- AUT-1853: `/data` default (snap dockerd masks `/opt`)
- `docs/Security/security.md`: full security policy
