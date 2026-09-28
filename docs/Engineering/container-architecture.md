# Container Architecture

## Compose (dev) — 5 containers

`docker-compose.yml`: postgres, redis, minio, backend (API + AI gateway +
Celery worker+beat), frontend. Source volumes for hot reload. The AI gateway
runs as a sub-process on :8001 within the backend container (AUT-3461),
reducing the dev stack from 7 to 5 containers (AI gateway merged into backend).

## Compose (prod) — 5 containers

`docker-compose.prod.yml`: same core, ENVIRONMENT=production, no source
mounts, nginx reverse proxy published on :80, backend only exposed
internally. The backend image runs the API + AI gateway (:8001) + Celery
worker+beat in one container (AUT-2000). All services run `read_only: true`
with `cap_drop: ALL` + tmpfs mounts.

## Compose (hosted) — 10 containers

`docker-compose.hosted.yml`: prebuilt GHCR images pinned by digest
(`ghcr.io/cannonfodder151/autobrain-*:hosted`), Stripe billing, self-signup +
MFA enforced. Deployed via Portainer on the Oracle Cloud ARM64 VM.

| Service | Image | Role |
|---------|-------|------|
| postgres | `pgvector/pgvector:pg17` | PostgreSQL 17 datastore + `vector` extension (pgvector) |
| redis | `redis:7.2.5-alpine` | Cache + Celery broker/result backend (`requirepass` on) |
| minio | `minio/minio` | Receipts/photos S3 storage; bucket init folded into entrypoint |
| backend | `autobrain-backend:hosted` | API :8000 + AI gateway :8001 **+ Celery worker+beat** (AUT-3153) |
| dongle-server | `autobrain-dongle-server:hosted` | OBD ESP32 dongle firmware manifests + signed MinIO URLs + serial whitelist |
| frontend | `autobrain-frontend:hosted` | Static nginx-unprivileged :8080, localhost-bound :8086 behind Cloudflare/npm |
| hub | `autobrain-federation-hub:hosted` | Community Garage federation hub, deploy-only; code in private repo |
| gh-runner | `autobrain-gh-runner:arm64-latest` | ARM64 GitHub Actions self-hosted runner (built locally) |
| 9router | `decolua/9router:0.5.55` | OpenAI-compatible LLM router + embeddings; `0.0.0.0:20128` behind host firewall, external `9router-data` volume |
| autobrain-backup | `autobrain-backup:hosted` | Backup web GUI (restore + retention), localhost-bound :8080 |

The stack uses 10 long-running containers. Consolidation history:

- The standalone Celery `worker` service was merged into `backend` (AUT-3153):
  the backend image already carries the worker dependencies and its default CMD
  runs API + AI gateway + Celery worker+beat in one container, matching
  `docker-compose.prod.yml`.
- The separate `ai` container was also merged into `backend` (AUT-2000/AUT-3153)
  for the hosted stack — the AI gateway runs as a co-process on :8001 inside the
  backend container. The market-data scraper moved into backend Celery tasks
  (AUT-3810), which is why `docker/ai/Dockerfile` is no longer referenced here.
- The `backup-agent` service was removed (AUT-3827): the hourly snapshot push
  now runs as the `backup_offsite_hourly` Celery beat task in `backend`, pushing
  to `autobrain-backup`'s `/api/backup/ingest`.
- The dedicated `autobrain-worker` image is no longer built or published
  (AUT-3172); `docker/worker/Dockerfile` is retained on disk for k8s/legacy
  reference only.

## Image layout

Each app service runs as non-root (`autobrain` uid 1000), has a healthcheck, and
reads configuration exclusively from environment variables (secrets via
`*_FILE` bind mounts per AUT-1533).

- **backend** (`docker/backend/Dockerfile`): unified dev/prod image — API + AI
  gateway modules + Celery worker/beat entrypoint. The hosted command runs
  `python -m app.db.bootstrap`, then the Celery worker+beat in the background,
  then `uvicorn app.main:app` (AUT-3153). Runs as `autobrain:1000`.
- **dongle-server** (`docker/dongle-server/Dockerfile`): unified image — firmware
  distribution API + serial whitelist management. Runs as `autobrain:1000`.
- **frontend** (`docker/frontend/Dockerfile`): multi-stage build — Flutter web
  build → `nginxinc/nginx-unprivileged:stable-alpine` base. Runs as `nginx`
  user on :8080 (non-root). Healthcheck probes backend upstream.
- **hub** (`docker/hub/Dockerfile` in private repo): Python FastAPI service.
  Runs as `hub` user (non-root). Healthcheck via Python `urllib` GET `/health`.
- **9router** (`docker/runner/Dockerfile` wrapper): Node.js app on
  `decolua/9router:0.5.55`. Runs as non-root `node` user. Healthcheck not
  defined in compose (host firewall handles reachability).
- **autobrain-backup**: Go binary serving web GUI. Runs as non-root. Healthcheck
  not defined in compose.
- **gh-runner**: `ghcr.io/actions/actions-runner:latest` (multi-arch ARM64/AMD64)
  in a thin wrapper. Runs as root (requires `privileged: true` for docker.sock).

## Healthchecks

- backend: `curl -fsS http://localhost:8000/health` (the Celery worker+beat is a
  background process inside the same container; its health is covered by the
  backend healthcheck plus the worker log line).
- dongle-server: `curl -fsS http://localhost:8000/health`
- frontend: `wget -qO- "${BACKEND_URL:-http://backend:8000}/health" | grep -q '"status":"ok"'`
  (probes the backend upstream, not just nginx — AUT-2389).
- hub: Python `urllib` GET `http://localhost:8000/health`
- postgres/redis/minio: native probes (see compose)

## Vectorisation (pgvector)

Semantic search uses pgvector columns, installed by migrations
(`alembic: g7h8i9j0k1l2`, `h1i2j3k4l5m6`, `u1v2w3x4y5z6`). See
`docs/Engineering/ai/vector.md` for full schema and embedding pipeline.

- **Extension/columns:** `CREATE EXTENSION vector`; `embedding vector(1536)`
  columns on `diagnostics`, `service_records`, `modifications`, `receipts`,
  and `social_issue_posts` (dimension from `EMBEDDING_DIMENSION`, matching
  `text-embedding-3-small`).
- **Index:** `USING hnsw (embedding vector_cosine_ops)` — HNSW chosen over
  IVFFlat because it needs no list tuning/training on small per-user tables.
- **Embed-on-create:** API routes enqueue `queue_embedding` (Celery →
  `backfill_entity_embedding`); receipt OCR additionally embeds during
  `process_receipt`. Scheduled `backfill_entity_embeddings` covers drift.
- **Hybrid search:** `app/services/search.py` runs ILIKE keyword matches always,
  plus pgvector cosine distance (`a <=> b` cast to `vector`, bound parameter)
  when the query embedding succeeds via 9Router `/embeddings`. Results are
  deduped and ranked by score; keyword-only fallback if embeddings unavailable.
- Postgres image in hosted/dev/prod is `pgvector/pgvector:pg17` so the
  extension is available at migration time.

## Upgrade path (AUT-1847)

Instances (Demo, Default, Hosted) are upgraded via the **upgrade path** — a
deterministic, Portainer-API redeploy of each tier's stack in the mandated
promotion order (Demo → Default → Hosted, per AUT-107), with `pullImage` so the
freshly built images are actually pulled and changed services are recreated.
Health is verified per tier before promoting to the next.

Deployment is **not** blind/automatic (board direction, AUT-1847): CI publishes
the images; the `deploy-instances.yml` workflow then posts a Discord `#ops`
notification and **stops** — the Deployment Lead must trigger the actual upgrade
(`workflow_dispatch`) after confirming an image was published. The triggered job
runs `scripts/upgrade-instances.sh`.

1. CI publishes images on every merge to `main`:
   - `dockerhub-publish.yml` → Docker Hub `:latest` (Demo/Default backend/ai) +
     `:default` frontend.
   - `build-hosted.yml` → GHCR `:hosted` (Hosted).
2. On completion, the `notify` job of `deploy-instances.yml` posts to Discord
   `#ops` (author "Deployment Lead") that an image is published and ready to
   promote, with a link to the workflow dispatch. The `upgrade` job (Deployment
   Lead-triggered) then runs `scripts/upgrade-instances.sh`, which redeploys each
   stack via `PUT /api/stacks/{id}?endpointId={ep}&pullImage=true`
   (Portainer 2.45 — the `/redeem` sub-route does not exist here) with the
   stack's own compose + env and `Prune: false`, preserving volumes and config.
3. DB migrations run inside the backend container on boot
   (`python -m app.db.bootstrap` / Alembic), so a redeploy is a complete upgrade
   — no separate migration step.
4. After all tiers are healthy, `scripts/prune-images.sh` drops dangling
   build-layer images on EP2/EP5 (AUT-350).

Root cause that this fixes: previously CI only *built* images — nothing pulled
them, a Watchtower attempt on Portainer-Host had no registry credentials
(`watchtower-noaccess`) and Hosted had none at all, so redeploys were manual and
were missed. The Hosted stack also failed redeploys because its Portainer stack
env was missing the required `POSTGRES_USER`/`POSTGRES_DB`
(`docker-compose.hosted.yml` used `${VAR:?...}`); the compose now defaults those
non-secret vars so a redeploy can never fail at interpolation again. The earlier
auto-redeploy also omitted `pullImage`, so it re-applied the compose with the same
image digest and never actually pulled the new image — instances silently never
updated.