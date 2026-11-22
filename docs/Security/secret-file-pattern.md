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

## Kubernetes: Native Secret Objects

The Kubernetes manifests in `infra/k8s/` do **not** use the `_FILE` bind-mount pattern. Instead they use native Kubernetes `Secret` objects referenced via `envFrom.secretRef` and `valueFrom.secretKeyRef`. This is the canonical k8s approach — secrets are injected as environment variables by the kubelet, which stores them in tmpfs and never writes them to disk.

### Creating the Secret

Create the `autobrain-secrets` Secret out-of-band before applying any Deployment. Never commit real values to git:

```bash
kubectl create namespace autobrain
kubectl -n autobrain create secret generic autobrain-secrets \
  --from-literal=secret-key="$(openssl rand -hex 32)" \
  --from-literal=postgres-user=autobrain \
  --from-literal=postgres-password="$(openssl rand -hex 24)" \
  --from-literal=minio-access-key="$(openssl rand -hex 16)" \
  --from-literal=minio-secret-key="$(openssl rand -hex 24)" \
  --from-literal=redis-password="$(openssl rand -hex 24)"
```

For GitOps, manage this Secret with [SealedSecrets](https://github.com/bitnami-labs/sealed-secrets) or [external-secrets](https://external-secrets.io/).

### Referencing in Deployments

**Bulk injection** (all keys as env vars):

```yaml
envFrom:
  - secretRef:
      name: autobrain-secrets
  - configMapRef:
      name: autobrain-config
```

**Single key** (for constructing URLs or passing to specific containers):

```yaml
env:
  - name: POSTGRES_PASSWORD
    valueFrom:
      secretKeyRef:
        name: autobrain-secrets
        key: postgres-password
  - name: REDIS_PASSWORD
    valueFrom:
      secretKeyRef:
        name: autobrain-secrets
        key: redis-password
  - name: REDIS_URL
    value: redis://:$(REDIS_PASSWORD)@autobrain-redis:6379/0
```

### When to Use Which Pattern

| Pattern | Environment | Why |
|---------|-------------|-----|
| `_FILE` bind-mount | Docker Compose (dev, hosted EP5) | Secrets never visible in `docker inspect` or `/proc/*/environ`; works with images that have native `*_FILE` support |
| Native k8s Secret | Kubernetes (`infra/k8s/`) | Kubelet-managed tmpfs, RBAC integration, native `secretKeyRef`/`envFrom` — no custom entrypoint wrapper needed |

If migrating a k8s deployment to the `_FILE` pattern (e.g. for consistency with docker-compose), mount the Secret as a volume:

```yaml
volumes:
  - name: secrets
    secret:
      secretName: autobrain-secrets
      defaultMode: 0400
containers:
  - name: backend
    volumeMounts:
      - name: secrets
        mountPath: /run/secrets
        readOnly: true
    env:
      - name: POSTGRES_PASSWORD_FILE
        value: /run/secrets/postgres-password
```

## Rotation Procedures

### Docker Compose (Hosted EP5)

1. **Update the secret file** on the host:
   ```bash
   sudo sh -c 'echo -n "newpassword" > /data/autobrain/secrets/postgres_password'
   sudo chown root:1000 /data/autobrain/secrets/postgres_password
   sudo chmod 0640 /data/autobrain/secrets/postgres_password
   ```
2. **Restart consuming services:**
   ```bash
   cd /path/to/autobrain
   docker compose -f docker-compose.hosted.yml up -d --force-recreate postgres backend worker
   ```
   For broker password rotation, restart `redis`, `backend`, and `worker` together.
3. **Verify:**
   ```bash
   docker exec <backend-container> env | grep POSTGRES_PASSWORD  # should show new value
   docker exec <postgres-container> psql -U autobrain -c 'SELECT 1'  # should succeed
   ```

**No image rebuild is needed** — secrets are runtime-mounted files.

### Kubernetes

1. **Update the Secret:**
   ```bash
   kubectl -n autobrain create secret generic autobrain-secrets \
     --from-literal=postgres-password="$(openssl rand -hex 24)" \
     --dry-run=client -o yaml | kubectl apply -f -
   ```
2. **Restart pods** to pick up the new Secret value:
   ```bash
   kubectl -n autobrain rollout restart deployment/autobrain-backend
   kubectl -n autobrain rollout restart deployment/autobrain-worker
   ```
   For Postgres password changes, restart `autobrain-postgres` as well (the entrypoint re-initialises on password mismatch).
3. **Verify:**
   ```bash
   kubectl -n autobrain exec deploy/autobrain-backend -- printenv POSTGRES_PASSWORD
   kubectl -n autobrain logs deploy/autobrain-postgres --tail=20
   ```

### Rotation Checklist

- [ ] Generate new secret value with sufficient entropy (`openssl rand -hex 24` minimum)
- [ ] Update the secret in Paperclip secret store (if using `seed-secrets.sh`)
- [ ] Update the runtime secret (file on host for Docker, Secret object for k8s)
- [ ] Restart all consuming services
- [ ] Verify service health (`docker ps` / `kubectl get pods`)
- [ ] Verify the old value no longer works (negative test)
- [ ] Update any external systems that hold the old value (webhooks, CI secrets)

## Security Properties

| Property | Guarantee |
|----------|-----------|
| No secrets in `docker inspect` | Secrets are in bind-mounted files, not env vars |
| No secrets in CI logs | Seed script runs on host, not in CI |
| No secrets in image layers | Secrets mounted at runtime only |
| Least privilege | Files `0640`, owned by `root:1000` (Docker) or tmpfs + RBAC (k8s) |
| Audit trail | Paperclip secret store tracks access |
| No secrets in git | All secret files and k8s Secrets are out-of-band; repo has placeholders only |

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
