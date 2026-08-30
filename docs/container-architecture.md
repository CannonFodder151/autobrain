# Container Architecture

## Compose (dev)

`docker-compose.yml`: postgres, redis, minio, backend (reload, runs API +
Celery worker+beat), ai (reload), market-data (separate scraper service).
Source volumes for hot reload.

## Compose (prod)

`docker-compose.prod.yml`: same core, ENVIRONMENT=production, no source
mounts, nginx reverse proxy published on :80, backend/ai only exposed
internally. Backend runs the API + Celery worker+beat in one container;
market-data merged into the ai image (AUT-1242/C3).

## Compose (hosted) — 9 containers

`docker-compose.hosted.yml`: prebuilt tagged images
(`ghcr.io/cannonfodder151/autobrain-*:hosted`), Stripe billing env vars,
self-signup + MFA enforced. Deployed via Portainer on the Oracle Cloud VM.

| Service | Image | Role |
|---------|-------|------|
| postgres | `pgvector/pgvector:pg16` | Datastore + `vector` extension (pgvector) |
| redis | `redis:7-alpine` | Cache + Celery broker/result backend |
| minio | `minio/minio` | Receipts/photos S3 storage |
| backend | `autobrain-backend:hosted` | API + WebSocket on :8000 |
| ai | `autobrain-ai:hosted` | AI gateway :8001 + market-data scraper :8000 in one container (AUT-1242/C3) |
| worker | `autobrain-worker:hosted` | Celery worker + beat (`-B`), single container (AUT-1242/C1) |
| frontend | `autobrain-frontend:hosted` | Static nginx, localhost-bound :8086 behind Cloudflare/npm |
| hub | `autobrain-federation-hub:hosted` | Federation hub, deploy-only; code in private repo |
| 9router | `decolua/9router:latest` | LLM router + embeddings; localhost-bound :20128, external `9router-data` volume |

Plus a one-shot `minio-init` job (`minio/mc`) that creates buckets at boot.
The stack uses 9 long-running containers; the Celery worker+beat is **not**
inside backend here (it was split out in AUT-1242/C1 by a dedicated worker
image built from the backend app).

## Image layout

Each service runs as non-root (`autobrain` uid 1000), has a healthcheck, and
reads configuration exclusively from environment variables.

- **backend** (`docker/backend/Dockerfile`): unified dev/prod image — API + AI
  gateway modules + Celery worker/beat entrypoint.
- **ai** (`docker/ai/Dockerfile`): entrypoint runs two uvicorn processes —
  market-data scraper on :8000 and AI gateway on :8001 (AUT-1242/C3).
- **worker** (`docker/worker/Dockerfile`): standalone production image from
  `backend/app`; CMD `celery -A app.workers.celery_app:celery_app worker -B -l
  info --concurrency=2`.

## Healthchecks

- backend: `curl -fsS /health`
- ai: `curl -fsS http://localhost:8001/health && curl -fsS http://localhost:8000/health`
- worker: `celery inspect ping`; beat-aware branch checks `celerybeat-schedule`
  freshness (AUT-601).
- hub: python `urllib` GET `/health`
- postgres/redis/minio: native probes (see compose)

## Vectorisation (pgvector)

Semantic search uses pgvector columns, installed by migrations
(`alembic: g7h8i9j0k1l2`, `h1i2j3k4l5m6`).

- **Extension/columns:** `CREATE EXTENSION vector`; `embedding vector(1536)`
  columns on `diagnostics`, `service_records`, `modifications`, `receipts`
  (dimension from `EMBEDDING_DIMENSION`, matching `text-embedding-3-small`).
- **Index:** `USING hnsw (embedding vector_cosine_ops)` — HNSW chosen over
  IVFFlat because it needs no list tuning/training on small per-user tables.
- **Embed-on-create:** API routes enqueue `queue_embedding` (Celery →
  `backfill_entity_embedding`); receipt OCR additionally embeds during
  `process_receipt`. Scheduled `backfill_entity_embeddings` covers drift.
- **Hybrid search:** `app/services/search.py` runs ILIKE keyword matches always,
  plus pgvector cosine distance (`a <=> b` cast to `vector`, bound parameter)
  when the query embedding succeeds via 9Router `/embeddings`. Results are
  deduped and ranked by score; keyword-only fallback if embeddings unavailable.
- Postgres image in hosted/dev/prod is `pgvector/pgvector:pg16` so the
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