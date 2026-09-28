# AutoBrain — System Overview

AutoBrain is an AI-powered car enthusiast companion. Users manage multiple vehicles and track everything about them: maintenance, fuel, modifications, diagnostics, parts inventory and receipts — with an AI layer providing diagnostics, service prediction, OCR extraction, resale valuation and mod impact analysis.

## Components

| Component | Role |
|-----------|------|
| **Flutter app** | iOS/Android client. Offline-first, local SQLite cache. |
| **FastAPI backend** | REST + WebSocket API, auth, business logic, exports. |
| **PostgreSQL (pgvector)** | Primary datastore; `vector` columns power semantic search. |
| **Redis** | Cache + Celery broker/result backend (auth required). |
| **MinIO** | S3-compatible object storage for receipts and photos. |
| **Celery worker + beat** | Async OCR processing, embedding generation, scheduled valuations, reorder suggestions, off-site backup push. Runs inside the backend container on all topologies. |
| **AI gateway (FastAPI)** | Hosts 12 deterministic-first inference modules; 9Router enrichment via `AI_ROUTER_URL`. Runs inside the backend container on :8001. |
| **Market-data scraper** | Playwright-based price/valuation scraper. Runs as Celery tasks in the backend (AUT-3810). |
| **Dongle server** | OBD ESP32 dongle firmware manifests + signed MinIO URLs + serial whitelist (AUT-1673). |
| **Federation hub** | Community Garage federation hub — deploy-only config in this repo; code lives in the private `autobrain-federation-hub` repo. Hosted stack only. |
| **9Router** | External LLM router that powers AI modules and embeddings when configured. Hosted stack runs a local instance on `0.0.0.0:20128` behind host firewall. |
| **autobrain-backup** | Backup web GUI (restore + retention), localhost-bound :8080. |
| **gh-runner** | ARM64 GitHub Actions self-hosted runner (built locally, `privileged: true`). |

## Deployment topologies

| Topology | Compose file | Notes |
|----------|--------------|-------|
| Dev      | `docker-compose.yml` | Source mounts, reload, all ports exposed; worker+beat in backend container |
| Prod     | `docker-compose.prod.yml` | Nginx frontend, no exposed ports except :80; worker+beat in backend container |
| Hosted   | `docker-compose.hosted.yml` | Prebuilt GHCR images, Stripe, self-signup, Oracle Cloud ARM64 VM; 10 containers |
| Kubernetes | `infra/k8s/` | Ingress, 2 replicas, secrets |
| Bare metal | `infra/systemd/` | Container-backed systemd units |

### Hosted stack (10 containers)

postgres · redis · minio · backend (API :8000 + AI gateway :8001 + Celery worker+beat) · dongle-server · frontend (:8080 in container, localhost-bound :8086) · hub · gh-runner · 9router (`0.0.0.0:20128` behind firewall) · autobrain-backup (localhost-bound :8080)

## Data flow (AI)

```
Client request
    │
    ▼
Backend API route (e.g. /diagnostics)
    │
    ▼
ai_client.run_diagnostics(payload)
    │
    ▼
HTTP POST http://localhost:8001/v1/diagnostics
    │
    ▼
AI gateway modules.diagnostics.run(payload)
    │
    ├─▶ fallbacks.diagnose_fallback(payload)  ← ALWAYS runs (deterministic baseline)
    │
    └─▶ router_client.enhance("diagnostics", baseline)
          │
          ├─▶ 9Router available? → POST /chat/completions (OpenAI format, temp 0)
          │    │
          │    ├─▶ Yes: shallow-merge enrichment, skip _AI_IMMUTABLE keys
          │    └─▶ No / error / timeout: return baseline untouched
          │
          ▼
Result with `model` field: `rule-based-fallback` | `rule-based+ai` | `rrp-depreciation`
```

**Key invariant:** The deterministic baseline always produces a valid result. 9Router is an optional enrichment layer — never a dependency.

## Vector search (pgvector)

PostgreSQL 17 with `pgvector/pgvector:pg17` image. Five tables carry `embedding vector(1536)` columns with HNSW cosine-similarity indexes:

- `diagnostics` — symptoms + AI response summary
- `service_records` — description + notes + steps
- `modifications` — name + notes + category
- `receipts` — vendor + extracted line-item names
- `social_issue_posts` — title + body (Community Garage)

Search is hybrid: keyword ILIKE always runs; vector cosine similarity layers on top when the query embedding succeeds via 9Router `/embeddings`. Keyword-only fallback if embeddings unavailable.

See `docs/Engineering/ai/vector.md` for full schema and embedding pipeline.

## Security posture

- All app containers run as non-root (`autobrain` uid 1000) except `nginx-unprivileged` (nginx user) and `gh-runner` (root, requires `privileged: true` for docker.sock).
- Redis requires auth (`requirepass` via secret file).
- MinIO requires auth (`MINIO_ROOT_USER/PASSWORD` via secret files).
- 9Router on `0.0.0.0:20128` protected by host firewall (`fw-keeper`): allow-listed dev egress IP + internal docker subnet only.
- Secrets loaded via `*_FILE` bind mounts from `/data/autobrain/secrets` (AUT-1533); never appear in env or `docker inspect`.
- Postgres/Redis/MinIO images pinned by digest for supply-chain hardening.

## Observability

- Healthchecks on all services (see `container-architecture.md`).
- Portainer stack health per endpoint.
- Discord `#status` channel for live service status.
- Weekly digest to Discord `#roadmap`.