# Container Consolidation — Migration Checklist (AUT-3153)

Phase 1(a): reduce the number of containers in the AutoBrain stack.

## Scope

- **Target:** `docker-compose.hosted.yml` (Portainer stack `autobrain-hosted`,
  endpoint 5, Oracle Cloud VM 152.69.188.133).
- **Change:** merge the standalone Celery `worker` service into `backend`.
  The backend image already carries the worker dependencies and its default
  CMD runs API + Celery worker+beat in one container (see
  `docker/backend/Dockerfile` and `docker-compose.prod.yml`).
- **Result:** hosted stack drops from 9 to 8 long-running containers
  (13 total services → 12). The worker's fuel-poll environment moves to the
  backend; the worker image is no longer referenced by this stack.

## What is already consolidated

- Market-data scraper runs inside the `ai` image (`docker/ai/Dockerfile`,
  `docker-compose.hosted.yml` `ai` service) — AUT-1242/C3.
- MinIO bucket initialization runs inside the `minio` service entrypoint —
  AUT-1242/C2. There is no separate `minio-init` sidecar in the hosted stack.
- Celery beat runs inside the worker (`-B`) — AUT-1242/C1.

## Pre-deploy

- [ ] Open a PR with the consolidated `docker-compose.hosted.yml` and this
      checklist. Get QA + Security sign-off; auto-merge fires per AUT-2230.
- [ ] Confirm the new `backend` image digest (with Celery support) is
      published to GHCR and multi-arch (amd64 + arm64). The hosted backend
      image already contains the Celery app and dependencies.
- [ ] Confirm the hosted Portainer stack env still carries the required
      non-secret vars (`POSTGRES_USER`, `POSTGRES_DB`) and the secret files
      under `/data/autobrain/secrets` (see `scripts/seed-secrets.sh`).
- [ ] Confirm the `FUEL_*` secret files are seeded:
      `fuel_nsw_api_key`, `fuel_nsw_api_secret`, `fuel_vic_api_key`,
      `fuel_vic_api_secret`, `fuel_qld_api_key`, `fuel_sa_api_key`.
      The worker's fuel-poll env moved into the backend service.
- [ ] Confirm the `AI_ROUTER_API_KEY` secret file is seeded and the backend
      command still exports it for `config.py` (which reads the plain var).

## Deploy (promotion order — do not skip tiers)

1. **Demo** → verify `/health`, backend logs, Celery worker+beat startup,
   fuel-poll tasks, and MinIO bucket private.
2. **Default** → same verification.
3. **Hosted** (Portainer EP5) → re-apply `docker-compose.hosted.yml` with
   `pullImage=true` (via `scripts/upgrade-instances.sh` or the Portainer API),
   then verify.

The compose re-apply removes the standalone `worker` container and recreates
`backend` with the merged command.

## Verify

- [ ] `backend` is healthy: `curl -fsS http://localhost:8000/health` →
      `{"status":"ok", ...}`.
- [ ] Backend logs show `celery` worker started with beat (`-B`) and
      `alembic_migrations_applied` after `python -m app.db.bootstrap`.
- [ ] Celery tasks still run: trigger a fuel-poll task or inspect the beat
      schedule; confirm no duplicate worker processes.
- [ ] AI gateway still serves on `http://ai:8001` (the `ai` service is
      unchanged).
- [ ] MinIO bucket `autobrain-assets` exists and is private (`mc anonymous
      get` → `none`).
- [ ] `worker` container no longer exists in the hosted stack.
- [ ] `docker-compose.hosted.yml` service list has no `worker` service.

## Rollback

If the merged backend fails health or task execution:

1. Stop the rollout at the failing tier (AUT-107).
2. Re-apply the previous `docker-compose.hosted.yml` (with the standalone
   `worker` service) from the previous commit / Portainer stack history.
3. Redeploy the tier and verify `/health` + Celery tasks.
4. Keep the DB volume and MinIO volume — they are untouched by this change.

## Follow-ups (child issues)

- **Retire the standalone `autobrain-worker` image build** from
  `.github/workflows/build-hosted.yml` and `.github/workflows/dockerhub-publish.yml`
  (the hosted stack no longer references it; k8s already uses
  `autobrain-backend:latest`).
- **Consolidate MinIO init into the `minio` entrypoint for `docker-compose.prod.yml`
  and `docker-compose.yml`** (they still run the one-shot `/init-minio.sh` from
  the backend command).
- **Align the dev `ai` service** to run the full `docker/ai/entrypoint.sh`
  (market-data + AI gateway) instead of the gateway-only command override,
  so dev parity matches prod/hosted.
