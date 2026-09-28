# Container Consolidation — Migration Checklist (AUT-3153, AUT-3810, AUT-3824, AUT-3827)

Phase 1(a): reduce the number of containers in the AutoBrain stack.

## Scope

- **Target:** `docker-compose.hosted.yml` (Portainer stack `autobrain-hosted`,
  endpoint 5, Oracle Cloud VM <HOSTED_VM_IP>).
- **Changes:**
  - Merge standalone Celery `worker` service into `backend` (AUT-3153).
  - Merge standalone `ai` gateway service into `backend` (AUT-3824).
  - Merge `market-data` scraper into `backend` Celery tasks (AUT-3810).
  - Remove standalone `backup-agent` service; hourly snapshot push runs as Celery beat task in `backend` (AUT-3827).
  - MinIO bucket init folded into `minio` entrypoint (AUT-1242/C2).
- **Result:** hosted stack reduced from 12 → **10 long-running containers**.
  Remaining: postgres, redis, minio, backend (API:8000 + AI:8001 + Celery), dongle-server, frontend, hub, gh-runner, 9router, autobrain-backup.

## What is consolidated

| Service | Status | Details |
|---------|--------|---------|
| `worker` (Celery) | **Merged** (AUT-3153) | Backend image runs `celery worker -B` alongside API. `docker/worker/Dockerfile` retained as reference only. |
| `ai` (AI gateway) | **Merged** (AUT-3824) | `ai_app.main:app` co-process on :8001 inside `backend`. No separate `ai` service. |
| `market-data` (fuel scraper) | **Merged** (AUT-3810) | Runs as local Celery beat tasks in `backend`. `shm_size: 256m` added for Chromium. |
| `minio-init` | **Merged** (AUT-1242/C2) | Runs inside `minio` entrypoint; no sidecar. |
| `backup-agent` | **Removed** (AUT-3827) | Hourly off-site backup push is a Celery beat task in `backend` (`app.workers.tasks.backup_offsite_hourly`). |

## Pre-deploy

- [ ] Open a PR with the consolidated `docker-compose.hosted.yml` and this
      checklist. Get QA + Security sign-off; auto-merge fires per AUT-2230.
- [ ] Confirm the new `backend` image digest (with Celery + AI gateway) is
      published to GHCR and multi-arch (amd64 + arm64). The hosted backend
      image already contains the Celery app, AI gateway, and dependencies.
- [ ] Confirm the hosted Portainer stack env still carries the required
      non-secret vars (`POSTGRES_USER`, `POSTGRES_DB`) and the secret files
      under `/data/autobrain/secrets` (see `scripts/seed-secrets.sh`).
- [ ] Confirm the `FUEL_*` secret files are seeded:
      `fuel_nsw_api_key`, `fuel_nsw_api_secret`, `fuel_vic_api_key`,
      `fuel_vic_api_secret`, `fuel_qld_api_key`, `fuel_sa_api_key`.
      The market-data scraper env moved into the backend service.
- [ ] Confirm the `AI_ROUTER_API_KEY` secret file is seeded and the backend
      command still exports it for `config.py` (which reads the plain var).
- [ ] Confirm backup off-site keys are seeded:
      `backup_offsite_gui_key`, `backup_offsite_ingest_key`.

## Deploy (promotion order — do not skip tiers)

1. **Demo** → verify `/health`, backend logs, Celery worker+beat startup,
   AI gateway on :8001, fuel-poll tasks, backup-offsite task, MinIO bucket private.
2. **Default** → same verification.
3. **Hosted** (Portainer EP5) → re-apply `docker-compose.hosted.yml` with
   `pullImage=true` (via `scripts/upgrade-instances.sh` or the Portainer API),
   then verify.

The compose re-apply removes the standalone `worker`, `ai`, `market-data`, `backup-agent` containers and recreates `backend` with the merged command.

## Verify

- [ ] `backend` is healthy: `curl -fsS http://localhost:8000/health` →
      `{"status":"ok", ...}`.
- [ ] AI gateway is reachable: `curl -fsS http://backend:8001/health` (internal) → `{"status":"ok"}`.
- [ ] Backend logs show `celery` worker started with beat (`-B`) and
      `alembic_migrations_applied` after `python -m app.db.bootstrap`.
- [ ] Celery tasks still run: trigger a fuel-poll task or inspect the beat
      schedule; confirm no duplicate worker processes.
- [ ] Backup off-site hourly task runs: check Celery beat schedule for `offsite-backup-hourly`.
- [ ] MinIO bucket `autobrain-assets` exists and is private (`mc anonymous
      get` → `none`).
- [ ] No `worker`, `ai`, `market-data`, or `backup-agent` containers exist in the hosted stack.
- [ ] `docker-compose.hosted.yml` service list has no `worker`, `ai`, `market-data`, or `backup-agent` service.
- [ ] Container count is 10 (postgres, redis, minio, backend, dongle-server, frontend, hub, gh-runner, 9router, autobrain-backup).

## Rollback

If the merged backend fails health or task execution:

1. Stop the rollout at the failing tier (AUT-107).
2. Re-apply the previous `docker-compose.hosted.yml` (with the standalone
   `worker`, `ai`, `market-data`, `backup-agent` services) from the previous commit / Portainer stack history.
3. Redeploy the tier and verify `/health` + Celery tasks.
4. Keep the DB volume and MinIO volume — they are untouched by this change.

## Follow-ups (child issues)

- **Consolidate `autobrain-backup` GUI + internal cron** into a single backup service (target: -1 container, total 9).
- **Consolidate MinIO init into the `minio` entrypoint for `docker-compose.prod.yml`
  and `docker-compose.yml`** (they still run the one-shot `/init-minio.sh` from
  the backend command).
- **Align the dev `ai` service** to run the full `docker/ai/entrypoint.sh`
  (market-data + AI gateway) instead of the gateway-only command override,
  so dev parity matches prod/hosted.