# Container Consolidation Migration (Phase 1 Workstream A)

> **Status**: Current as of v0.3.278 (main, 2026-09-26). Tracks the consolidation of AutoBrain docker services from 14+ containers down to 10 in hosted, 5 in prod/dev.

---

## Executive Summary

| Environment | Before (pre-Phase 1) | After (current main) | Reduction |
|-------------|---------------------|----------------------|-----------|
| **Hosted (EP5, Oracle VM)** | 14 containers | 10 containers | -29% |
| **Prod (self-hosted)** | 8 containers | 5 containers | -38% |
| **Dev (docker-compose.yml)** | 6 containers | 5 containers | -17% |

---

## Hosted Stack (docker-compose.hosted.yml) — Current State (10 services)

| Service | Image | Role | Notes |
|---------|-------|------|-------|
| `postgres` | `pgvector/pgvector:pg17@sha256:cf134a767f...` | Primary DB + pgvector | Healthcheck: `pg_isready` |
| `redis` | `redis:7.2.5-alpine@sha256:6aaf3f5e6b...` | Cache + Celery broker | Auth via `redis_password` secret |
| `minio` | `minio/minio@sha256:14cea493d9...` | S3 object storage | Auto-creates bucket at boot |
| `backend` | `ghcr.io/cannonfodder151/autobrain-backend:hosted@sha256:14543848e3...` | **API :8000 + AI Gateway :8001 + Celery worker/beat** | Consolidated service (AUT-2000, AUT-3827) |
| `autobrain-backup` | `ghcr.io/cannonfodder151/autobrain-backup:hosted@sha256:e76fac3c69...` | **Unified backup service** (PostgreSQL + MinIO) | Consolidated from `backup-agent` + `autobrain-backup` (AUT-3979, AUT-3944) |
| `dongle-server` | `ghcr.io/cannonfodder151/autobrain-dongle-server:hosted@sha256:c5768948a9...` | Firmware distro + serial whitelist | Shares MinIO/Postgres |
| `frontend` | `ghcr.io/cannonfodder151/autobrain-frontend:hosted@sha256:02ed10e3b1...` | Static nginx on :8086 (localhost) | Behind Cloudflare/npm |
| `hub` | `ghcr.io/cannonfodder151/autobrain-federation-hub:hosted@sha256:d1d9bde1f1...` | Federation hub (private repo) | Deploy config only |
| `gh-runner` | `ghcr.io/cannonfodder151/autobrain-gh-runner:arm64-latest` | Self-hosted ARM64 GitHub Actions runner | Replaces amd64-only myoung34 runner |
| `9router` | `decolua/9router:0.5.55@sha256:f00fe389ef...` | LLM router + embeddings on :20128 | External `9router-data` volume |

### Key Consolidation Changes (Hosted)

| Change | PR / Issue | Description |
|--------|-----------|-------------|
| AI gateway merged into backend | AUT-2000, PR #757 | Backend now runs `uvicorn ai_app.main:app --port 8001` as co-process |
| Celery worker+beat merged into backend | AUT-3827, PR #757 | Backend command includes `celery ... worker -B` |
| `backup-agent` + `autobrain-backup` → single `autobrain-backup` | AUT-3944, AUT-3979, PR #757 | One container handles both Postgres dump + MinIO sync |
| `docker/worker/` directory deleted | AUT-3826 | Dead code removed after worker merged into backend |
| `minio-init` sidecar removed | AUT-1242/C2 | Bucket init folded into minio server entrypoint |
| ARM64 self-hosted runner added | AUT-2469 | `ghcr.io/actions/actions-runner` multi-arch image |

---

## Prod Stack (docker-compose.prod.yml) — Current State (5 services)

| Service | Image | Role |
|---------|-------|------|
| `postgres` | `pgvector/pgvector:pg17` | Primary DB + pgvector |
| `redis` | `redis:7.2.5-alpine` | Cache + Celery broker |
| `minio` | `minio/minio` | S3 object storage |
| `backend` | Built from source (`docker/backend/Dockerfile`) | **API :8000 + AI Gateway :8001 + Celery worker/beat** |
| `frontend` | Built from source (`docker/frontend/Dockerfile`) | Static nginx on :80 |

### Prod Consolidation Notes

- Single `backend` image runs everything: API, AI gateway (co-process on :8001), Celery worker+beat (via `-B`)
- No separate `ai`, `worker`, `backup`, `hub`, `9router`, `dongle-server`, `gh-runner` services
- Self-hosters deploy 9router/hub/dongle-server separately if needed

---

## Dev Stack (docker-compose.yml) — Current State (5 services)

| Service | Image | Role |
|---------|-------|------|
| `postgres` | `pgvector/pgvector:pg17` | Primary DB + pgvector |
| `redis` | `redis:7.2.5-alpine` | Cache + Celery broker |
| `minio` | `minio/minio` | S3 object storage |
| `backend` | Built from source, hot-reload | **API :8000 + AI Gateway :8001 + Celery worker/beat** |
| `frontend` | Built from source, hot-reload | Vite/Flutter dev server |

---

## Migration Path for Existing Deployments

### Hosted (EP5) — Already Migrated

The hosted stack at **main v0.3.278+** is already on the consolidated 10-container topology. No further action needed beyond routine redeploys.

**Redeploy checklist:**
1. Portainer EP5 → Stack `autobrain-hosted` → Redeploy with `pullImage=true`
2. Verify all 10 containers healthy: `docker ps --format "table {{.Names}}\t{{.Status}}"`
3. Health endpoints:
   - Backend: `https://hosted.autobrainservice.app/health`
   - AI Gateway: `https://hosted.autobrainservice.app/ai/health` (proxied via nginx)
   - Frontend: `https://hosted.autobrainservice.app`
   - 9Router: `http://152.69.188.133:20128/health` (internal only)

### Prod / Self-Hosted — Migration Required

Self-hosters on old `docker-compose.yml` with separate `ai` + `worker` services must migrate:

```bash
# 1. Backup
docker compose down
cp -r /opt/autobrain/data /opt/autobrain/data.bak

# 2. Switch to docker-compose.prod.yml (or updated docker-compose.yml v0.3.278+)
# The new compose has backend running API + AI + Celery in one container

# 3. Remove old volumes (worker, ai) if they exist
docker volume rm autobrain_worker-data 2>/dev/null || true
docker volume rm autobrain_ai-data 2>/dev/null || true

# 4. Deploy
docker compose -f docker-compose.prod.yml up -d --build

# 5. Verify
docker compose ps
curl -f http://localhost/health
curl -f http://localhost/ai/health
```

### Dev — Update Local Compose

```bash
git pull origin main
docker compose down
docker compose up -d --build
```

---

## Verification: Container Count

```bash
# Hosted (EP5)
ssh administrator@152.69.188.133 "docker ps --filter name=autobrain-hosted --format '{{.Names}}' | wc -l"
# Expected: 10

# Prod
docker compose -f docker-compose.prod.yml ps --services | wc -l
# Expected: 5

# Dev
docker compose ps --services | wc -l
# Expected: 5
```

---

## Rollback Plan

If consolidation causes regressions:

1. **Hosted**: `git revert <merge-commit>` → rebuild images → redeploy via Portainer with old image tags
2. **Prod/Dev**: `git checkout <pre-consolidation-tag>` → `docker compose up -d --build`
3. Data volumes are untouched (postgres-data, redis-data, minio-data persist)

---

## Related Issues

- AUT-3810 — Phase 1 master tracker
- AUT-3811 — Reduce container count in docker-compose stacks (in_review)
- AUT-3824 — Merge ai gateway into backend container (blocked)
- AUT-3827 — Consolidate backup-agent into backend Celery beat (in_progress)
- AUT-3826 — Delete docker/worker directory dead code (blocked)
- AUT-3944 — Consolidate autobrain-backup + backup-agent (blocked)
- AUT-3979 — Fix docker-compose.hosted.yml duplicate volumes key (done)
- AUT-3908 — Verify container count reduction end-to-end on EP5 (blocked)

---

## Next Targets (Phase 1+)

| Target | Estimated Reduction | Blockers |
|--------|---------------------|----------|
| Remove `hub` from hosted (externalize) | -1 | Federation hub must be independently deployable |
| Move `gh-runner` to separate VM | -1 | Oracle VM resources; runner needs docker socket |
| Co-locate `9router` with backend (internal) | -1 | 9Router needs public :20128 for dev egress; firewall complexity |
| **Theoretical minimum** | **7 containers** | postgres, redis, minio, backend, frontend, dongle-server, hub* |

*hub could move to separate federation stack.

---

*Generated by CEO heartbeat (AUT-3925). Keep current with each consolidation PR.*
