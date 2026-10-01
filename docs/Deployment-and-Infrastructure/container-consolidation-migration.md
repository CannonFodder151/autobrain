# Container Consolidation — Migration Checklist (AUT-3153, AUT-3810, AUT-3824, AUT-3827)

Phase 1(a): reduce the number of containers in the AutoBrain stack.

## Exception — EP2 personal/non-AutoBrain containers STAY (AUT-4502, board directive 2026-09-29)

**Do NOT move personal apps off Portainer endpoint 2 (Portainer-Host, 10.0.3.17).**
Nathan denied the AUT-4502 migration plan in writing: *"DO NOT move these. Add an
exception — not to move containers off this host. Default is for my use only."*

EP2 carries both the AutoBrain Demo + Default stacks and Nathan's personal
self-hosted services. The personal set is **in scope for hosting on EP2 and out
of scope for every container-consolidation, migration and image-prune task.**
Container count on EP2 is therefore *not* a consolidation KPI — do not derive
"remove N containers" work from it.

Personal / non-AutoBrain containers on EP2 (as of 2026-09-29; 37 containers total
on the host):

| Group | Containers |
|-------|-----------|
| Photos | `immich_server`, `immich_machine_learning`, `immich_postgres`, `immich_redis` |
| Game hosting | `pterodactyl-panel-panel-1`, `pterodactyl-panel-database-1`, `pterodactyl-panel-cache-1` |
| Media / *arr | `Prowlarr`, `Ombi`, `Huntarr`, `FlareSolverr` |
| Network | `UniFi-OPSAT`, `unifi-fubar`, `unifi-mongo` |
| Apps | `mealie`, `Whoogle-Search`, `cards-against-docker`, `Headroom`, `Stirling-PDF`, `Draw.io` |
| Platform / tooling | `Grafana`, `n8n-n8n-1`, `n8n-traefik-1`, `outline`, `outline-postgres`, `outline-redis`, `portainer`, `portainer-mcp`, `watchtower-noaccess-watchtower-1`, `9Router` |

Rules:

- **No migration.** Do not create a "personal services host" for these. EP2 is
  Nathan's host; its personal services are permanent there.
- **No consolidation.** Do not merge, containerise or refactor personal
  containers as part of AutoBrain work.
- **No pruning.** `scripts/prune-images.sh` and any EP2 image/cleanup pass must
  **exclude images used by the personal containers listed above**. Prune
  AutoBrain images only (`cannonfodder151/autobrain-*`,
  `ghcr.io/cannonfodder151/*`).
- **No redeploys.** Per the AUT-2409 promotion override, EP2 (Demo + Default)
  deploys stay paused; that pause also covers these personal stacks.
- Any future request to "tidy up" EP2 requires a new, explicit board directive
  from Nathan. This exception is only lifted by that directive.

## Scope

- **Target:** `docker-compose.hosted.yml` (Portainer stack `autobrain-hosted`,
  endpoint 5, Oracle Cloud VM <HOSTED_VM_IP>).
- **Changes:**
  - Merge standalone Celery `worker` service into `backend` (AUT-3153).
  - Merge standalone `ai` gateway service into `backend` (AUT-3824).
  - Merge `market-data` scraper into `backend` Celery tasks (AUT-3810).
  - Remove standalone `backup-agent` service; hourly snapshot push runs as Celery beat task in `backend` (AUT-3827).
  - Rename the `autobrain-backup` GUI service to `backup` so the compose service, docker DNS name and image repo agree (AUT-3944).
  - MinIO bucket init folded into `minio` entrypoint (AUT-1242/C2).
- **Result:** hosted stack reduced from 12 → **9 long-running containers**.
  Remaining: postgres, redis, minio, backend (API:8000 + AI:8001 + Celery), dongle-server, frontend, hub, 9router, backup. (`gh-runner` was removed in AUT-4911; it runs as its own Portainer stack.)

## What is consolidated

| Service | Status | Details |
|---------|--------|---------|
| `worker` (Celery) | **Merged** (AUT-3153) | Backend image runs `celery worker -B` alongside API. `docker/worker/Dockerfile` retained as reference only. |
| `ai` (AI gateway) | **Merged** (AUT-3824) | `ai_app.main:app` co-process on :8001 inside `backend`. No separate `ai` service. |
| `market-data` (fuel scraper) | **Merged** (AUT-3810) | Runs as local Celery beat tasks in `backend`. `shm_size: 256m` added for Chromium. |
| `minio-init` | **Merged** (AUT-1242/C2) | Runs inside `minio` entrypoint; no sidecar. |
| `backup-agent` | **Removed** (AUT-3827) | Hourly off-site backup push is a Celery beat task in `backend` (`app.workers.tasks.backup_offsite_hourly`). |
| `autobrain-backup` | **Renamed → `backup`** (AUT-3944) | One backup container serves the GUI; the cron that used to live in the agent sidecar runs in `backend` beat. GUI still on `127.0.0.1:8080`. |

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
- [ ] Container count is 9 (postgres, redis, minio, backend, dongle-server, frontend, hub, 9router, backup).
- [ ] No container or network alias named `autobrain-backup` remains; the
      GUI resolves at `http://backup:8080` from inside the stack.
- [ ] `BACKUP_OFFSITE_URL` on the EP5 stack env is either unset (compose
      default `http://backup:8080`) or explicitly `http://backup:8080` — a
      stale `http://autobrain-backup:8080` override silently stops hourly
      pushes (AUT-3944).
- [ ] An hourly snapshot appears in the GUI backup list (task
      `offsite-backup-hourly`, `crontab(minute=0)`).
- [ ] `python3 scripts/check-compose-consolidation.py` passes.
- [ ] Automated check (live endpoint, needs `PORTAINER_API_KEY`):
      `python3 scripts/verify-hosted-containers.py --endpoint 5 --stack autobrain-hosted`
      → `OK: 10 containers match docker-compose.hosted.yml` (exit 0). It fails on any
      missing, extra, or non-running container, so it also covers the three
      `No worker/ai/market-data/backup-agent` lines above.

## Rollback

If the merged backend fails health or task execution:

1. Stop the rollout at the failing tier (AUT-107).
2. Re-apply the previous `docker-compose.hosted.yml` (with the standalone
   `worker`, `ai`, `market-data`, `backup-agent` services) from the previous commit / Portainer stack history.
3. Redeploy the tier and verify `/health` + Celery tasks.
4. Keep the DB volume and MinIO volume — they are untouched by this change.

## Follow-ups (child issues)

- **Consolidate MinIO init into the `minio` entrypoint for `docker-compose.prod.yml`
  and `docker-compose.yml`** (they still run the one-shot `/init-minio.sh` from
  the backend command).
- **Align the dev `ai` service** to run the full `docker/ai/entrypoint.sh`
  (market-data + AI gateway) instead of the gateway-only command override,
  so dev parity matches prod/hosted.