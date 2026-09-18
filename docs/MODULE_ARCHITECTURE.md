# AutoBrain Module Architecture

## Overview

AutoBrain is a three-layer monorepo with clear boundaries:

```
┌─────────────────────────────────────────────────┐
│                    Frontend                       │
│                  (Flutter/Dart)                   │
│   HTTP/WS calls → backend API (no direct DB)     │
└──────────────────┬──────────────────────────────┘
                   │ HTTP :8000 / WS :8000
┌──────────────────▼──────────────────────────────┐
│                  Backend                          │
│          (FastAPI + Celery + Redis)               │
│   api/ → routes & DI                            │
│   services/ → business logic (framework-free)    │
│   models/ → SQLAlchemy ORM                       │
│   schemas/ → Pydantic validation                 │
│   core/ → config, security, cache, storage       │
│   social/ → Community Garage domain              │
│   workers/ → Celery async jobs                   │
└──────────────────┬──────────────────────────────┘
                   │ HTTP :8001 (localhost only)
┌──────────────────▼──────────────────────────────┐
│                 AI Gateway                        │
│       (FastAPI — runs inside backend container)   │
│   modules/ → AI module registry (12 modules)     │
│   fallbacks/ → deterministic rule-based engines   │
│   router_client.py → 9Router integration         │
└──────────────────┬──────────────────────────────┘
                   │ :9292 / :5432 / :9000
┌──────────────────▼──────────────────────────────┐
│              Infrastructure                       │
│   PostgreSQL (db)  Redis  MinIO (storage)        │
└─────────────────────────────────────────────────┘
```

## Package Dependency Graph

All arrows are top-level imports only. Runtime imports inside function bodies break cycles where needed.

```
api.v1 ──────► core, db, models, schemas, services, social, workers
core   ◄────── everything (no outbound deps)
db     ──────► core, models (seed only), social (never)
models ──────► db (Base, types), social.models (feature config in __init__)
schemas ─────► core, models
services ────► core, db, models, schemas, social, workers (fuel->tasks)
social ──────► api.deps, core, db, models, services (auth.client_ip)
middleware ──► core, services
workers ─────► core, db, models, services, ws
```

### Known Cross-Package Dependencies (Accepted)

| Dependency | File | Reason | Status |
|------------|------|--------|--------|
| `models → db.session`, `db.types` | All models | SQLAlchemy Base + custom types | ✅ Expected |
| `db.seed → models.*` | `app/db/seed.py` | Seed data needs model classes | ✅ Expected |
| `models.__init__ → social.models` | `app/models/__init__.py` | Re-export social config models | ✅ Acceptable |
| `services.search → social.models` | `app/services/search.py` | Federated search across domains | ✅ Acceptable |
| `social.rate_limit → services.auth` | `app/social/rate_limit.py` | Shared `client_ip` utility | ✅ Acceptable |
| `social.rate_limit → api.deps` | `app/social/rate_limit.py` | Shared DI deps (`require_premium_write`) | ✅ Intentional |
| `api.v1.* → social.*` | `issues.py`, `social.py` | API routes use social domain logic | ✅ Expected |
| `services.fuel → workers.tasks` | `app/services/fuel.py` | Queue embeddings from service layer | ⚠️ Revisit (services→workers) |
| `workers.tasks → services.ai_client, search` | `app/workers/tasks.py` | Workers execute async service work | ⚠️ Revisit (workers→services) |

The `services ↔ workers` cycle is the only one needing refactor (AUT-3464 follow-up).

## Module Boundaries

| Package | Owns | Imports From | Never Imports |
|---------|------|-------------|---------------|
| `core` | Config, logging, security, GPS utils, cache, storage | — (leaf) | nothing |
| `db` | SQLAlchemy session, Base, migrations, seed | core, models (seed) | api, services, social, workers |
| `models` | ORM models (User, Vehicle, SocialBuild, …) | db (Base, types), social.models (in __init__) | api, services, workers |
| `schemas` | Pydantic request/response schemas | core, models | api, services, social, workers |
| `services` | Business logic (rate limit, auth, fuel, billing, …) | core, db, models, schemas, social, workers | api |
| `social` | Community Garage domain logic (federation, media, rate limit) | api.deps, core, db, models, services | workers, frontend, api.v1.* |
| `api` | FastAPI routers, DI dependencies | core, db, models, schemas, services, social | workers |
| `middleware` | Request middleware (rate limiting) | core, services | — |
| `workers` | Celery tasks (async jobs) | core, db, models, services, ws | api, social |
| `ai` | Inference gateway, AI modules, fallbacks | 9Router client only | backend |

## Rules

1. **No circular top-level imports.** Runtime imports inside function bodies are permitted only to break unavoidable cycles (e.g. `social ↔ issues` via lazy import).
2. **`core/` is a leaf.** It imports nothing from other packages. Put shared utils here.
3. **`api/` never calls `services` directly for DI.** Dependencies live in `api/deps.py` or `api/rate_deps.py`; services expose pure functions.
4. **`services/` is framework-free.** No FastAPI, no Pydantic — just async functions with explicit parameters. This enables testing without HTTP.
5. **`ai/` is a separate process boundary.** It talks to `backend` only via HTTP :8001. No shared DB, no shared Redis, no shared models.
6. **`social/` may import `api.deps`** for shared DI utilities (`require_premium`, `require_premium_write`, `require_social_feature`) but never other `api.v1.*` routers.
7. **`models/` may import `social.models`** only for feature-config tables that live in the social domain.

## AI Gateway Modules

| Module | Deterministic Fallback | AI Enhancement |
|--------|----------------------|----------------|
| `advisor` | Rule-based service schedule | 9Router context analysis |
| `car-check` | Manufacturer recall DB + rules | 9Router risk scoring |
| `condition` | Wear model from mileage/age | 9Router condition assessment |
| `diagnostics` | OBD code → known fixes | 9Router diagnostic reasoning |
| `fuel-ocr` | Tesseract local OCR | 9Router receipt parsing |
| `odometer` | Tesseract + digit detection | 9Router validation |
| `ocr` | Tesseract receipt extraction | 9Router field enrichment |
| `resale` | Depreciation curves + market data | 9Router valuation reasoning |
| `service-prediction` | Manufacturer schedules | 9Router predictive analysis |
| `mod-impact` | Rule-based impact scoring | 9Router market analysis |
| `parts-guide` | Parts catalog lookup | 9Router recommendation |
| `social-image` | Local image processing | 9Router caption generation |

## Container Topology

After AUT-3461 consolidation:

```
docker-compose.yml (dev):
  backend    — API + AI gateway + Celery worker+beat
  postgres
  redis
  minio
  frontend

docker-compose.prod.yml / hosted.yml:
  backend    — API + AI gateway + Celery worker+beat
  ai         — market-data scraping only (Playwright/Chromium)
  postgres
  redis
  minio
  frontend
```

The `ai` service remains separate in prod only for Playwright/Chromium memory isolation (market-data scraping requires ~256MB `/dev/shm`). The inference gateway runs inside the `backend` container.

## Phase 1 Modularity Improvements (AUT-3464)

Completed in this issue:
- ✅ **Rate limit separation**: `services/rate_limit.py` (pure logic) + `api/rate_deps.py` (FastAPI DI) — broke `services → api` import
- ✅ **Cache extraction**: `core/cache.py` (`TTLCache` class) — moved from `services/ai_client.py`, reusable across gateway & backend
- ✅ **Docker consolidation**: AI gateway merged into `backend` container (AUT-3461) — reduced container count from 5 to 4 in dev
- ✅ **Circular import fix**: Moved `require_social_feature` to `api/deps.py` — broke `api.v1.issues ↔ api.v1.social` cycle
- ✅ **Module graph documented**: This file + `scripts/check-module-deps.py`

Follow-up work (new issues):
- 📋 **services ↔ workers cycle**: Extract task queue interface to `core/queue.py` so services don't import workers
- 📋 **Vector storage**: Add pgvector-based embedding store for semantic search (Phase 1b)
- 📋 **AI determinism audit**: Review all 12 AI modules for "deterministic first, AI fallback" pattern (Phase 1c)

## Generated

Run `python3 scripts/check-module-deps.py` to validate architecture.