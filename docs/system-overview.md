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
| **PostgreSQL** | Primary datastore. |
| **Redis** | Cache + Celery broker/result backend. |
| **MinIO** | S3-compatible object storage for receipts and photos. |
| **Celery worker + beat** | Async OCR processing, scheduled valuations, reorder suggestions. Runs inside the backend container. |
| **AI gateway (FastAPI)** | Hosts 7 deterministic-first inference modules; 9Router enrichment via `AI_ROUTER_URL`. |
| **9Router** | External LLM router that powers AI modules when configured. |

## Deployment topologies

| Topology | Compose file | Notes |
|----------|-------------|-------|
| Dev | `docker-compose.yml` | Source mounts, reload, all ports exposed |
| Prod | `docker-compose.prod.yml` | Nginx frontend, no exposed ports except :80 |
| Hosted | `docker-compose.hosted.yml` | Prebuilt Docker Hub images, Stripe, self-signup, Oracle Cloud VM |
| Kubernetes | `infra/k8s/` | Ingress, 2 replicas, secrets |
| Bare metal | `infra/systemd/` | Container-backed systemd units |

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
