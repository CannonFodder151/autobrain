# Secret-File Pattern (*_FILE) — AUT-1533

AutoBrain mounts secrets as **files** (not environment variables) in containers. Environment variable names ending in `_FILE` point to a bind-mounted secret file; the application reads the file at startup and injects the value into process env. Secrets never appear in `docker inspect`, `docker compose config`, or image layers.

---

## Pattern

| Convention | Meaning |
|------------|---------|
| `FOO` | Plain environment variable (non-secret config) |
| `FOO_FILE` | Path to a file containing the secret value; app reads it at startup |

Example from `docker-compose.hosted.yml`:

```yaml
environment:
  POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
```

The file is bind-mounted:

```yaml
volumes:
  - type: bind
    source: ${SECRETS_DIR:-/data/autobrain/secrets}/postgres_password
    target: /run/secrets/postgres_password
    read_only: true
```

---

## Application Code

Config classes load `_FILE` variants transparently:

```python
# app/core/config.py
POSTGRES_PASSWORD: str = Field(..., env="POSTGRES_PASSWORD_FILE")
```

Pydantic settings reads the file content automatically when the `_FILE` env var is set. Plain env vars are still used for non-secret values.

---

## Secret Files Location

| Environment | Secret directory | Mounted at |
|-------------|-----------------|------------|
| Dev / Demo / Default | `${SECRETS_DIR}` (defaults to `/data/autobrain/secrets`) | `/run/secrets` in container |
| Hosted (Oracle EP5) | `/data/autobrain/secrets` | `/run/secrets` in container |

The hosted stack uses `/data` (not `/opt`) because the snap dockerd on Oracle Cloud masks `/opt` as a read-only core24 squashfs — binds to `/opt` fail (AUT-1853).

---

## Seeding Secrets

Run `scripts/seed-secrets.sh` before deploying. It reads Paperclip secrets and writes them to `${SECRETS_DIR}` as individual files with mode `0640`, owned by root.

Required secret files for hosted:

```
postgres_password, minio_access_key, minio_secret_key, redis_password,
backend_secret_key, ai_router_api_key, ai_gateway_api_key,
admin_initial_password, smtp_username, smtp_password,
fuel_nsw_api_key, fuel_nsw_api_secret, fuel_vic_api_key, fuel_vic_api_secret,
fuel_qld_api_key, fuel_sa_api_key,
backup_offsite_gui_key, backup_offsite_ingest_key,
admin_api_key, stripe_secret_key, stripe_webhook_secret,
iap_google_service_account_json, iap_apple_private_key,
dongle_server_api_key, dongle_web_basic_password,
rego_lookup_api_key, hub_hosted_registration_key
```

---

## Security Properties

- Secrets are **not in image layers** — they are bind-mounted at runtime.
- `docker inspect` does **not** reveal secret values.
- Secret files are mounted `read_only: true`.
- The host directory (`/data/autobrain/secrets`) should be `0700` root-owned.
- Rotation: update the file, restart the container; no image rebuild needed.

---

## See Also

- `docs/security.md` — full security policy including broker auth
- `docker/lib-load-secrets.sh` — container startup secret loader
- `scripts/seed-secrets.sh` — secret provisioning script
