# AutoBrain — Module Architecture & Boundaries

This document defines the backend module graph, dependency rules, and the
refactoring work shipped in AUT-3464 (Phase 1 code review).

## Module Graph (simplified)

```
┌───────────────────────────────────────────────────────┐
│  api/       FastAPI routers + dependencies             │
│  api/v1/    route handlers                             │
│  api/deps.py     auth + role dependencies              │
│  api/rate_deps.py  rate-limit DI wrappers              │
└───────┬───────────────────────────────────────────────┘
        │ imports FROM (never the reverse)
        ▼
┌───────────────────────────────────────────────────────┐
│  services/  business logic (framework-free)            │
│    ai_client.py        HTTP gateway client             │
│    rate_limit.py       pure Redis counter logic        │
│    trip_gps.py         CSV → samples parser            │
│    ownership.py        vehicle access control           │
│    fuel.py / fuel_servo.py / parts_guide.py / ...     │
└───────┬───────────────────────────────────────────────┘
        │ imports FROM (never the reverse)
        ▼
┌───────────────────────────────────────────────────────┐
│  core/      shared utilities, zero framework deps      │
│    config.py    pydantic Settings                      │
│    cache.py     generic TTLCache                       │
│    gps.py       GPS sample cleaning (clean_samples)   │
│    logging.py   structured logging                     │
│    storage.py   MinIO / S3 helpers                     │
│    security.py  JWT / password hashing                 │
└───────────────────────────────────────────────────────┘
        │ imports FROM (never the reverse)
        ▼
┌───────────────────────────────────────────────────────┐
│  models/    SQLAlchemy ORM models                      │
│  schemas/   Pydantic request/response models           │
└───────────────────────────────────────────────────────┘
```

## Dependency Direction (one-way only)

```
api → services → core
api → models
api → schemas
schemas → core          (clean_samples only, no services import)
services → core
services → models
```

**Forbidden directions:**
- `core` → anything else (core is leaf, zero deps)
- `services` → `api` (no service depends on FastAPI layer)
- `schemas` → `services` (schemas depend only on core utilities)
- `models` → anything except the database driver

## Key Refactoring (AUT-3464)

### 1. Rate Limit: services → api dependency eliminated

**Before:** `services/rate_limit.py` imported `FastAPI.Depends` and `app.api.deps.get_current_user`.
**After:** Pure Redis counter logic stays in `services/rate_limit.py`; FastAPI DI wrappers
moved to `api/rate_deps.py`. API routers import from `api/rate_deps`, not `services.rate_limit`.

```
api/rate_deps.py  →  services/rate_limit.py  →  core/config.py
                (DI wrappers)           (pure Redis logic)
```

### 2. GPS cleaning: schemas → services dependency eliminated

**Before:** `schemas/device.py` and `schemas/logbook.py` imported `clean_samples` from
`services/trip_gps.py` (creating schema → service dependency).
**After:** `clean_samples` lives in `core/gps.py` (framework-free); both schemas and
`services/trip_gps.py` import from core.

```
schemas/device.py  →  core/gps.py  ←  services/trip_gps.py
schemas/logbook.py →               ←
```

### 3. Cache extracted from ai_client

**Before:** `ai_client.py` contained two near-identical 60-line TTL cache implementations
(advisor + car-check).
**After:** Generic `TTLCache` class in `core/cache.py` with pre-configured instances
`advisor_cache` and `car_check_cache`. ai_client imports and uses them.

## New Files Created

| File | Purpose |
|------|---------|
| `backend/app/core/gps.py` | GPS sample cleaning — shared by schemas + services |
| `backend/app/core/cache.py` | In-process TTL cache with LRU eviction |
| `backend/app/api/rate_deps.py` | FastAPI dependency wrappers for rate limiting |
| `docs/modularity-architecture.md` | This document |

## Import Rules (for new code)

1. **Service functions must not import from FastAPI.** If a service needs to be a
   route dependency, create a thin DI wrapper in `api/rate_deps.py` or `api/deps.py`.
2. **Schemas must not import from services.** Shared validation utilities go in `core/`.
3. **Core modules must not import from services, api, or schemas.**
4. **AI gateway calls go through `services/ai_client.py`.** The backend never calls
   the AI gateway directly — it uses the HTTP client abstraction.
5. **Deterministic logic runs first, AI is fallback.** Each AI module runs its
   deterministic baseline first, then calls 9Router via `enhance()`. The
   `enhance()` function never modifies immutable fields (see `_AI_IMMUTABLE`).

## Social Module

`social/` is a self-contained subdomain within the backend:
- `social/rate_limit.py` — in-process sliding window (no Redis dependency)
- `social/models.py` — SQLAlchemy social models
- `social/federation.py` — hub client
- `social/media.py` — image processing (no AI)
- `social/snapshot.py` — deterministic build snapshots
- `social/tags.py` — deterministic tag vocabulary

Import rule: `api/v1/social.py` and `api/v1/issues.py` import from `social/`.
Services do not import from `social/` (the coupling is at the API layer only).
