# Container Architecture

## Compose (dev) — 5 containers

`docker-compose.yml`: postgres, redis, minio, backend (API + AI gateway +
Celery worker+beat), frontend. Source volumes for hot reload. The AI gateway
runs as a sub-process on :8001 within the backend container (AUT-3461),
reducing the dev stack from 7 to 5 containers (AI gateway merged into backend).

## Compose (prod)

`docker-compose.prod.yml`: same core, ENVIRONMENT=production, no source
mounts, nginx reverse proxy published on :80, backend only exposed
internally. Backend runs the API + AI gateway + Celery worker+beat in one
container (AUT-3461). Market-data scraper runs as Celery tasks in backend
(AUT-3810). The separate `ai` image/service was removed (AUT-3461).

## Compose (hosted) — 10 containers

`docker-compose.hosted.yml`: prebuilt tagged images
(`ghcr.io/cannonfodder151/autobrain-*:hosted`), Stripe billing env vars,
self-signup + MFA enforced. Deployed via Portainer on the Oracle Cloud VM (ARM64).

| Service | Image | Role |
|---------|-------|------|
| postgres | `pgvector/pgvector:pg17@sha256:cf134a76...` | Datastore + `vector` extension (pgvector), digest-pinned |
| redis | `redis:7.2.5-alpine@sha256:6aaf3f5e...` | Cache + Celery broker/result backend, auth required |
| minio | `minio/minio@sha256:14cea493...` | Receipts/photos S3 storage, digest-pinned |
| backend | `autobrain-backend:hosted@sha256:14543848...` | API :8000 + AI gateway :8001 + Celery worker+beat (AUT-3153), non-root |
| dongle-server | `autobrain-dongle-server:hosted@sha256:c5768948...` | OBD ESP32 dongle firmware + serial whitelist (AUT-1673), non-root |
| frontend | `autobrain-frontend:hosted@sha256:02ed10e3...` | Static nginx-unprivileged :8080, localhost-bound, non-root |
| hub | `autobrain-federation-hub:hosted@sha256:d1d9bde1...` | Federation hub (Community Garage), deploy-only; private repo |
| 9router | `decolua/9router:0.5.55@sha256:f00fe389...` | LLM router + embeddings on 0.0.0.0:20128, host-firewalled, external `9router-data` volume |
| backup | `autobrain-backup:hosted@sha256:e76fac3c...` | Backup web GUI, localhost-bound :8080, non-root. Service renamed from `autobrain-backup` in AUT-3944; hourly snapshot push runs in the backend Celery beat (AUT-3827), so there is no backup-agent sidecar. |
| gh-runner | `autobrain-gh-runner:arm64-latest` | ARM64 GitHub Actions self-hosted runner (privileged, AUT-2469) |

The stack uses 10 long-running containers. The standalone Celery worker+beat
service was merged into `backend` (AUT-3153): the backend image already carries
the worker dependencies and its default CMD runs API + Celery worker+beat in
one container, matching `docker-compose.prod.yml`. The dedicated
`autobrain-worker` image is no longer referenced by this stack; its build is
retired from CI (AUT-3172). The `ai` gateway service was consolidated into
`backend` (AUT-3461): the backend container runs the AI gateway as a
co-process on :8001. All application services run as non-root (`autobrain` uid
1000) with `read_only`, `cap_drop: ALL`, and `tmpfs` mounts.

## Image layout

Each service runs as non-root (`autobrain` uid 1000), has a healthcheck, and
reads configuration exclusively from environment variables.

- **backend** (`docker/backend/Dockerfile`): unified dev/prod image — API + AI
  gateway modules + Celery worker/beat entrypoint. The hosted command runs
  `python -m app.db.bootstrap`, then the Celery worker+beat in the background,
  then `uvicorn app.main:app` (AUT-3153).
- **ai** (`docker/ai/Dockerfile`): entrypoint runs two uvicorn processes —
  market-data scraper on :8000 and AI gateway on :8001 (AUT-1242/C3).
- **worker** (`docker/worker/Dockerfile`): standalone production image from
  `backend/app`. Retained on disk only for k8s/legacy reference; CI no longer
  builds or publishes it (AUT-3153 + AUT-3172). The hosted stack and k8s
  `infra/k8s/worker.yaml` both run the Celery worker+beat from the
  `autobrain-backend` image (`autobrain-backend:latest`), not the standalone
  worker image.

## Healthchecks

- backend: `curl -fsS /health` (the Celery worker+beat is a background process
  inside the same container; its health is covered by the backend healthcheck
  plus the worker log line).
- ai: `curl -fsS http://localhost:8001/health && curl -fsS http://localhost:8000/health`
- hub: python `urllib` GET `/health`
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