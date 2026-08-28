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

## Upgrade path

- Deploys are run manually from the repo: `docker compose -f docker-compose.prod.yml build && up -d`, or via `scripts/deploy.sh`. `docker compose up -d` is zero-downtime for backend/ai since nginx routes to running containers.
- DB migrations run inside the backend container on boot (`app.db.bootstrap`) in all topologies, including hosted.