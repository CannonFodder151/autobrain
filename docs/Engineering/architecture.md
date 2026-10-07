# Architecture

```
┌────────────┐  HTTPS / WSS      ┌───────────────────────────────┐
│  Flutter   │──────────────────▶│  nginx (reverse proxy :80)    │
│ iOS/Android│◀──────────────────│  /api -> backend:8000         │
└────────────┘                   │  /ws   -> backend:8000        │
                                 │  /ai   -> backend:8001        │
                                 └──────────────┬────────────────┘
                                                │
                     ┌──────────────────────────┼──────────────────────────┐
                     ▼                          ▼                          ▼
             ┌──────────────┐          ┌──────────────┐           ┌──────────────┐
             │  backend     │          │  9Router     │           │  frontend    │
             │  FastAPI     │          │  LLM router  │           │  nginx static│
             │  :8000 API   │          │  + embedding │           └──────────────┘
             │  :8001 AI    │          │  :20128      │
             │  + worker    │          └──────────────┘
             └──────┬───────┘
                    │  REST/WS
         ┌──────────┼──────────┐
         ▼          ▼          ▼
     PostgreSQL   Redis      MinIO
     (pgvector)  (cache/     (S3)
                 broker)
         ▲          ▲
         └──────────┘
```

## Deployment topologies

- **Dev:** single `docker-compose.yml` with source mounts + reload. 5 containers:
  postgres, redis, minio, backend (API + AI gateway + Celery worker+beat), frontend.
  Source volumes for hot reload.
- **Prod:** `docker-compose.prod.yml` behind nginx frontend container. Backend
  image runs API + AI gateway + Celery worker+beat in one container (see
  `docker/backend/Dockerfile`).
- **Hosted:** `docker-compose.hosted.yml` — 9 containers (postgres, redis, minio,
  backend, dongle-server, frontend, hub, 9router, backup).
  Prebuilt GHCR images (multi-arch amd64+arm64), Stripe billing, self-service
  signup, Portainer-managed on Oracle Cloud ARM64. The AI gateway runs inside
  the `backend` container on :8001 (AUT-3153); market-data scraper runs as Celery
  tasks in backend (AUT-3810). Application services run as non-root (backend/ai as
  `autobrain` uid 1000, frontend as `nginx`).
- **Kubernetes:** `infra/k8s/*` deployments + services + secrets.
- **Bare metal:** `infra/systemd/*` units (container-backed).

## Async processing

OCR receipt extraction runs in a Celery worker. The backend stores the file in
MinIO, enqueues `process_receipt`, and the worker calls the AI gateway's OCR
module, then persists extracted items and notifies the client over WebSocket
(`receipt.processed`). In dev/prod/hosted the worker runs inside the backend
container (AUT-3153). Scheduled tasks (valuations, reorder suggestions, off-site
backup push) come from the embedded beat scheduler, started with `worker -B`.

## High-level architecture (Mermaid)

```mermaid
graph TD
    Client[Flutter iOS/Android/Web] -->|HTTPS/WSS| Nginx[nginx :80]
    Nginx -->|/api /ws /ai| Backend[backend :8000/8001]
    Backend --> Postgres[(PostgreSQL pgvector)]
    Backend --> Redis[(Redis)]
    Backend --> MinIO[(MinIO S3)]
    Backend --> Queen[Celery broker queue in Redis]
    Backend -->|AI_ROUTER_URL + /embeddings| Router[9Router]
    Worker[Celery worker + beat (in backend container)] --> Queen
    Worker --> Postgres
    Search[App search: hybrid keyword + vector] --> Postgres
    Search --> Router
    Hub[hub - Federation Hub, deploy-only, hosted stack] -.-> Backend
```

## Vectorisation (pgvector)

Semantic search is backed by pgvector. The hosted PostgreSQL image is
`pgvector/pgvector:pg17@sha256:cf134a76...`. See `docs/Engineering/ai/vector.md` for the schema and embedding pipeline.