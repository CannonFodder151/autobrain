# AutoBrain — System Overview

AutoBrain is an AI-powered car enthusiast companion. Users manage multiple
vehicles and track everything about them: maintenance, fuel, modifications,
diagnostics, parts inventory and receipts — with an AI layer providing
diagnostics, service prediction, OCR extraction, resale valuation and mod
impact analysis.

## Components

| Component | Role |
|-----------|------|
| **Flutter app** | iOS/Android client. Offline-first, local SQLite cache. |
| **FastAPI backend** | REST + WebSocket API, auth, business logic, exports. |
| **PostgreSQL (pgvector)** | Primary datastore; `vector` columns power semantic search. |
| **Redis** | Cache + Celery broker/result backend. |
| **MinIO** | S3-compatible object storage for receipts and photos. |
| **Celery worker + beat** | Async OCR processing, embedding generation, scheduled valuations, reorder suggestions. Dev/prod: inside the backend container. Hosted: dedicated `worker` container (AUT-1242/C1). |
| **AI gateway (FastAPI)** | Hosts 7 deterministic-first inference modules; 9Router enrichment via `AI_ROUTER_URL`. |
| **Market-data scraper** | Playwright-based price/valuation scraper. Dev: separate `market-data` service. Prod/hosted: merged into the `ai` container on :8000 (AUT-1242/C3). |
| **Federation hub** | Community Garage federation hub — deploy-only config in this repo; code lives in the private `autobrain-federation-hub` repo. Hosted stack only. |
| **9Router** | External LLM router that powers AI modules and embeddings when configured. |

## Deployment topologies

| Topology | Compose file | Notes |
|----------|-------------|-------|
| Dev | `docker-compose.yml` | Source mounts, reload, all ports exposed; worker+beat in backend container |
| Prod | `docker-compose.prod.yml` | Nginx frontend, no exposed ports except :80; worker+beat in backend container |
| Hosted | `docker-compose.hosted.yml` | Prebuilt Docker Hub images, Stripe, self-signup, Oracle Cloud VM; 9 containers incl. dedicated `worker` |
| Kubernetes | `infra/k8s/` | Ingress, 2 replicas, secrets |
| Bare metal | `infra/systemd/` | Container-backed systemd units |

### Hosted stack (9 containers)

postgres · redis · minio · backend · ai (gateway :8001 + market-data :8000) ·
worker (Celery worker + beat) · frontend (:8086, localhost-bound behind
Cloudflare/npm) · hub · 9router (:20128, localhost-bound). A one-shot
`minio-init` job creates buckets at boot.

## Data flow (AI)

1. Backend receives a request (e.g. symptoms for diagnosis).
2. Backend calls the AI gateway at `AI_LOCAL_BASE_URL` (`http://ai:8001`).
3. The gateway runs its **deterministic rule engine first** (always produces a
   valid result), then optionally calls 9Router to enrich it when
   `AI_ROUTER_URL` is reachable — enrichment can never override measured
   ground-truth values.
4. If the router is unreachable, the deterministic result is returned as-is, so
   the platform never breaks.
5. Results are returned to the backend and stored (e.g. `diagnostics.ai_response`).

The result carries a `model` field (`rule-based-fallback` / `rrp-depreciation` /
`rule-based+ai`) so callers know which path produced it.

## Data flow (search)

Global search is hybrid keyword + vector: ILIKE keyword matching always runs;
pgvector cosine similarity (`a <=> b`, HNSW-indexed) runs when an embedding can
be generated via 9Router's `/embeddings`. Results are deduped and ranked by
combined score, falling back to keyword-only if embeddings are unavailable.
See `docs/container-architecture.md#vectorisation-pgvector`.

## Feature areas

- **Vehicle management** — profiles, rego lookup → VIN/make/model/year/engine, unified timeline.
- **Maintenance tracking** — service logs, AI prediction, PDF/CSV export.
- **Fuel tracker** — L/100km, cost/km, efficiency + cost graphs, AI insights.
- **AI diagnostics** — symptoms → causes, severity, parts, cost; add to next service.
- **Modification tracker** — AI impact summaries, build sheet export.
- **Receipt & parts scanner** — OCR extracts parts, labour, cost, warranty.
- **Parts inventory** — quantities, usage, AI reorder suggestions, link to services.
- **Resale value estimator** — value + trend + recommendations.
- **Analytics** — fuel/service/mod spend, total cost of ownership, cost/km, forecast.
