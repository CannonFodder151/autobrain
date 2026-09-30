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
| **backup** | Backup web GUI (restore + retention), localhost-bound :8080. Hourly off-site push is a backend Celery beat task (AUT-3827); service renamed from `autobrain-backup` in AUT-3944. |
| **gh-runner** | ARM64 GitHub Actions self-hosted runner (built locally, `privileged: true`). |

## Deployment topologies

| Topology | Compose file | Notes |
|----------|--------------|-------|
| **Dev** | `docker-compose.yml` | 5 containers, source mounts, hot reload, binds to 127.0.0.1 |
| **Prod** | `docker-compose.prod.yml` | 5 containers, nginx frontend :80, internal services only |
| **Hosted** | `docker-compose.hosted.yml` | 10 containers, GHCR multi-arch images, Oracle Cloud ARM64, Portainer EP5 |
| **Kubernetes** | `infra/k8s/*` | Deployments + services + secrets |
| **Bare metal** | `infra/systemd/*` | Container-backed systemd units |

All application containers run as non-root (uid 1000 `autobrain`) with `read_only: true`, `cap_drop: [ALL]`, and `tmpfs` mounts for writable paths.

## AI architecture (deterministic-first)

Every AI module runs a rule-based engine that always produces a valid result, then optionally enriches it via 9Router. The platform never depends on the router being up. See `ai-models.md`, `ai-router-integration.md`, and `module-breakdown.md`.

## Vector search (pgvector)

PostgreSQL 17 with `pgvector/pgvector:pg17@sha256:cf134a76...` (digest-pinned). Five tables carry `embedding vector(1536)` columns with HNSW cosine-similarity indexes. Hybrid search: keyword ILIKE always runs; vector cosine layers on top when 9Router `/embeddings` succeeds. See `ai/vector.md`.

## Federation (Community Garage)

Hosted stack includes a federation hub (`hub` service) that enables cross-instance social features. The hub code lives in the private `autobrain-federation-hub` repo; this repo only carries the deploy config. Hosted instances register with `SOCIAL_FEDERATION_HOSTED=true`.

## OBD2 dongle (phone-free logging)

Custom ESP32-based dongle (NodeMCU-32S + MCP2551 CAN transceiver + DS3231 RTC + NEO-8M GPS) plugs into the OBD-II port, logs trips to on-board flash, deep-sleeps on ignition-off, uploads via WiFi/BLE later. Firmware in `firmware/esp32-diy/`. Build guide: `obd2-dongle/nodemcu32s-build-guide.md`.