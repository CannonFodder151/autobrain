# Container Consolidation — Migration Checklist (AUT-3153)

Phase 1(a): reduce the number of containers in the AutoBrain stack.

## Scope

- **Target:** `docker-compose.hosted.yml` (Portainer stack `autobrain-hosted`,
  endpoint 5, Oracle Cloud VM <HOSTED_VM_IP>).
- **Change:** merge the standalone Celery `worker` service into `backend`.
  The backend image already carries the worker dependencies and its default
  CMD runs API + Celery worker+beat + AI gateway in one container (see
  `docker/backend/Dockerfile` and `docker-compose.prod.yml`).
- **Result:** hosted stack runs **9 long-running containers** (postgres,
  redis, minio, backend, dongle-server, frontend, hub, gh-runner,
  autobrain-backup). The standalone `worker` and `ai` services are removed;
  their workloads run inside `backend`.

## Current Hosted Stack Services (as of origin/main)

| Service | Purpose |
|---------|---------|
| `postgres` | pgvector/pgvector:pg17 (DB + vector store) |
| `redis` | Redis 7.2.5 (Celery broker, requires password) |
| `minio` | MinIO object storage (assets, backups, firmware) |
| `backend` | FastAPI + Celery worker+beat + AI gateway (port 8001) |
| `dongle-server` | OBD ESP32 firmware + serial whitelist |
| `frontend` | Flutter web build (nginx static) |
| `hub` | Community Garage federation hub |
| `gh-runner` | GitHub Actions self-hosted runner (ARM64) |
| `autobrain-backup` | Off-site backup ingestion API |

*Total: 9 containers. The `ai` service was removed (AUT-3825); the `worker`
service was removed (AUT-3153/AUT-3172).*

## What is consolidated

- **Market-data scraper** runs as local Celery tasks in `backend` — AUT-3825.
  No separate `ai` container. The `MARKET_DATA_URL` is intentionally unset so
  the local Playwright fallback is used.
- **MinIO bucket initialization** runs inside the `minio` service entrypoint —
  AUT-1242/C2. No separate `minio-init` sidecar.
- **Celery beat + worker** run inside `backend` (`celery -A ... worker -B`) —
  AUT-1242/C1 + AUT-3153.
- **AI gateway** runs inside `backend` on port 8001 (`uvicorn ai_app.main:app`)
  — AUT-3825.
- **Off-site backup push** runs as Celery beat task in `backend`
  (`backup_offsite_hourly`) — AUT-3827. The `autobrain-backup` service is the
  *receiver*; the *sender* is the backend task.

## Pre-deploy (for future changes to this stack)

- [ ] Open a PR with the updated `docker-compose.hosted.yml` and this
      checklist. Get QA + Security sign-off; auto-merge fires per AUT-2230.
- [ ] Confirm the `backend` image digest (with Celery + AI gateway) is
      published to GHCR and multi-arch (amd64 + arm64).
- [ ] Confirm the hosted Portainer stack env still carries the required
      non-secret vars (`POSTGRES_USER`, `POSTGRES_DB`) and the secret files
      under `/data/autobrain/secrets` (see `scripts/seed-secrets.sh`).
- [ ] Confirm the `FUEL_*` secret files are seeded:
      `fuel_nsw_api_key`, `fuel_nsw_api_secret`, `fuel_vic_api_key`,
      `fuel_vic_api_secret`, `fuel_qld_api_key`, `fuel_sa_api_key`.
      Fuel-poll env is now on the `backend` service.
- [ ] Confirm the `AI_ROUTER_API_KEY` secret file is seeded and the backend
      command still exports it for `config.py` (which reads the plain var).
- [ ] Confirm `BACKUP_OFFSITE_*` secrets are seeded for the off-site backup
      push from backend Celery beat.

## Deploy (promotion order — do not skip tiers)

1. **Demo** → verify `/health`, backend logs, Celery worker+beat startup,
   fuel-poll tasks, AI gateway on :8001, and MinIO bucket private.
2. **Default** → same verification.
3. **Hosted** (Portainer EP5) → re-apply `docker-compose.hosted.yml` with
   `pullImage=true` (via `scripts/upgrade-instances.sh` or the Portainer API),
   then verify.

## Verify

- [ ] `backend` is healthy: `curl -fsS http://localhost:8000/health` →
      `{"status":"ok", ...}`.
- [ ] Backend logs show `celery` worker started with beat (`-B`) and
      `alembic_migrations_applied` after `python -m app.db.bootstrap`.
- [ ] AI gateway responds on `http://localhost:8001/health` (served by
      `backend` container, not a separate `ai` service).
- [ ] Celery tasks still run: trigger a fuel-poll task or inspect the beat
      schedule; confirm no duplicate worker processes.
- [ ] MinIO bucket `autobrain-assets` exists and is private (`mc anonymous
      get` → `none`).
- [ ] `worker` container no longer exists in the hosted stack.
- [ ] `ai` container no longer exists in the hosted stack.
- [ ] `docker-compose.hosted.yml` service list has no `worker` or `ai` service.

## Rollback

If the merged backend fails health or task execution:

1. Stop the rollout at the failing tier (AUT-107).
2. Re-apply the previous `docker-compose.hosted.yml` (with the standalone
   `worker` and `ai` services) from the previous commit / Portainer stack
   history.
3. Redeploy the tier and verify `/health` + Celery tasks + AI gateway.
4. Keep the DB volume and MinIO volume — they are untouched by this change.

## Follow-ups (child issues)

- **Consolidate MinIO init into the `minio` entrypoint for
  `docker-compose.prod.yml` and `docker-compose.yml`** (they still run the
  one-shot `/init-minio.sh` from the backend command).
- **Remove the `docker/ai` directory** from the repo (no longer built or
  referenced; retained only for reference).
- **Review dev `docker-compose.yml` parity**: dev runs only postgres, redis,
  minio, backend, frontend. Prod/hosted additionally runs dongle-server,
  hub, gh-runner, autobrain-backup. Decide if dev should mirror more services
  for integration testing, or if the lighter stack is intentional.