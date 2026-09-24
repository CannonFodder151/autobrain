# Phase 1 Improvement Plan — AutoBrain Code Review & Improvement Initiative

**Prepared by:** CTO  
**Date:** 2026-09-24  
**Parent Issue:** [AUT-2000](/AUT/issues/AUT-2000) — Consolidate containers (Phase 1a)  
**Goal:** [4fc32f2e-2489-4333-aa9c-f04aafede71d](/AUT/projects/2e30f2ee-d92b-4f55-8b72-d884ceb2cd39) — Phase 1 Code Review & Improvement

---

## Executive Summary

Completed a comprehensive codebase review across backend/, ai/, frontend/, docker/, and docker-compose files. The stack has already made significant progress on container consolidation (backend+AI+worker merged in prod/dev). Remaining work focuses on the hosted stack, AI module hardening, modularisation, vector storage optimisation, and documentation refresh.

---

## (a) Reduce Container Count

### Current State

| Stack | Services | Containers |
|-------|----------|------------|
| **Dev** (docker-compose.yml) | postgres, redis, minio, backend, frontend | **5** |
| **Prod** (docker-compose.prod.yml) | postgres, redis, minio, backend, frontend | **5** |
| **Hosted** (docker-compose.hosted.yml) | postgres, redis, minio, backend, market-data, dongle-server, frontend, hub, gh-runner, 9router, autobrain-backup, backup-agent | **12** |

Dev/Prod already consolidated: backend runs uvicorn (API:8000) + uvicorn (AI gateway:8001) + Celery worker+beat in one container (AUT-2000, AUT-3153).

### Hosted Stack Consolidation Opportunities

| Service | Image | Purpose | Consolidation Path | Risk |
|---------|-------|---------|-------------------|------|
| `market-data` | autobrain-ai:hosted | Fuel price scraping (Chromium) | Move to Celery task in `backend`; add `shm_size: 256m` to backend | Medium (Chromium deps, shm) |
| `autobrain-backup` + `backup-agent` | autobrain-backup:hosted + autobrain-backup-agent:hosted | Backup GUI + hourly poller | Merge into single `backup` service; agent runs as cron inside backup container | Low |
| `dongle-server` | autobrain-dongle-server:hosted | Firmware distribution | Keep separate (distinct domain, separate repo) | — |
| `hub` | autobrain-federation-hub:hosted | Community Garage hub | Keep separate (private repo, separate image) | — |
| `gh-runner` | autobrain-gh-runner:arm64-latest | GitHub Actions ARM64 runner | Keep separate (privileged, docker.sock) | — |
| `9router` | decolua/9router:0.5.55 | AI inference router | Keep separate (infra component) | — |

### Target: Reduce hosted from 12 → **9 containers** (-3)

1. **Merge market-data into backend** (1 container) — move scraper to Celery beat task
2. **Merge backup + backup-agent** (1 container) — single backup service with internal cron
3. **Remove legacy worker reference** (already done in compose, CI build retired AUT-3172)

### Child Issues to Create

- `AUT-XXXX` Merge market-data scraper into backend Celery (hosted)
- `AUT-XXXX` Consolidate autobrain-backup + backup-agent into single backup service
- `AUT-XXXX` Verify container count reduction end-to-end on EP5 (smoke test)

---

## (b) Vectorise Data Storage

### Current State

**Vector store:** PostgreSQL + pgvector (pgvector/pgvector:pg17) — 5 tables with `vector(1536)` columns using `text-embedding-3-small` via 9Router.

| Table | Column | Content Embedded | Index |
|-------|--------|------------------|-------|
| `diagnostics` | `embedding` | Symptoms + AI response | HNSW |
| `service_records` | `embedding` | Description + notes + steps | HNSW |
| `modifications` | `embedding` | Name + notes + category | HNSW |
| `receipts` | `embedding` | Vendor + line-item names | HNSW |
| `social_issue_posts` | `embedding` | Title + body | HNSW |

**Search:** Hybrid — keyword (ILIKE) + vector (cosine similarity). Fallback to keyword-only when 9Router down.

**Embedding pipeline:** `backend/app/services/vector_search.py::generate_embedding` → 9Router `/embeddings` endpoint. Backfill via Celery task `backfill_entity_embeddings`.

### Gaps & Improvements

| Area | Issue | Action |
|------|-------|--------|
| **Dimension lock** | `EMBEDDING_DIMENSION` in config.py → migrations read at apply time — good | Verify all migrations use the setting |
| **Index type** | HNSW chosen — good for small per-user tables | Confirm all 5 indexes are HNSW (migration `h1i2j3k4l5m6` rebuilt IVFFlat → HNSW) |
| **Embedding model** | `text-embedding-3-small` (1536 dim) — hardcoded in router_utils as `EMBEDDING_MODEL` env var | Make dimension configurable via settings; document upgrade path for future models |
| **Vector search API** | `GET /api/v1/search` merges keyword + vector | Add per-entity-type vector weight tuning; expose similarity threshold |
| **Storage efficiency** | 1536-dim float32 = 6KB/row; ~50k rows = 300MB | Evaluate `halfvec` (float16) or binary quantization for cost reduction |
| **Query embedding caching** | Re-embeds same query repeatedly | Add Redis cache for query embeddings (TTL 1h) |

### Schema Upgrade Path

```sql
-- Future: add halfvec column alongside vector
ALTER TABLE diagnostics ADD COLUMN embedding_half halfvec(1536);
-- Backfill from vector column (cast)
UPDATE diagnostics SET embedding_half = embedding::halfvec;
-- Create HNSW index on halfvec
CREATE INDEX ON diagnostics USING hnsw (embedding_half halfvec_cosine_ops);
-- Switch search to halfvec, drop vector after validation
```

### Child Issues to Create

- `AUT-XXXX` Add Redis caching for query embeddings in vector_search.py
- `AUT-XXXX` Evaluate halfvec migration for storage reduction (PoC)
- `AUT-XXXX` Add vector search weight tuning per entity type
- `AUT-XXXX` Document embedding model upgrade procedure

---

## (c) Make AI Functions Deterministic-First with AI Fallback

### Current State — **EXCELLENT**

All 12 AI modules in `ai/app/modules/` already follow deterministic-first pattern:

| Module | Baseline Function | AI Enhancement | Immutable Keys |
|--------|-------------------|----------------|----------------|
| `diagnostics` | `diagnose_fallback()` | `enhance("diagnostics", ...)` | (none — AI enriches only) |
| `service-prediction` | `predict_service_fallback()` | `enhance("service-prediction", ...)` | (none) |
| `ocr` | `extract_receipt_fallback()` (Tesseract) | `enhance("ocr", ...)` | `vendor, invoice_date, total, tax, currency, items` |
| `resale` | `estimate_value_fallback()` | `enhance("resale", ...)` | `estimated_value, low, high, currency` |
| `mod-impact` | `mod_impact_fallback()` | `enhance("mod-impact", ...)` | `performance_score, value_impact, reliability_impact` |
| `condition` | `estimate_condition()` | `enhance("condition", ...)` | (none — AI adds summary only) |
| `fuel-ocr` | `_fuel_receipt_fallback()` (Tesseract) | `enhance("fuel-ocr", ...)` | `vendor, date, litres, price_per_litre, total_cost, currency` |
| `parts-guide` | `build_inventory_from_categories()` + `suggest_parts_for_service()` | `enhance("parts-guide", ...)` | `sku, service_group, supplier` (via schema) |
| `advisor` | `advisor_fallback()` | `enhance("advisor", ...)` | `decision, based_on` |
| `car-check` | `car_check_fallback()` | `enhance("car-check", ...)` | `deal_score, red_flags, green_flags` |
| `odometer` | `_odometer_fallback()` (Tesseract) | **NO AI CALL** — deterministic only | — |
| `social-image` | `render_card()` (Pillow) | Pollinations.ai (optional, explicit `prompt`) | — |

**Router client (`router_client.py`):** `enhance()` function enforces:
- Baseline always returned
- Router response merged only if `confidence >= MIN_AI_CONFIDENCE` (default 0.75)
- Immutable keys never overwritten
- Schema validation drops unknown/wrong-type keys
- Telemetry: `ai_path` = `deterministic` | `hybrid` | `router_error`

### Gaps to Close

| Module | Missing `_AI_IMMUTABLE` Entry | Action |
|--------|------------------------------|--------|
| `diagnostics` | None defined | Add critical fields: `summary, severity, items[*].cause, items[*].confidence, items[*].parts, items[*].estimated_cost` |
| `service-prediction` | None defined | Add: `service_type, interval_km, interval_months, next_due_km, next_due_date` |

### Child Issues to Create

- `AUT-XXXX` Add `_AI_IMMUTABLE` entries for `diagnostics` and `service-prediction` in `router_utils.py`
- `AUT-XXXX` Add corresponding `_SCHEMAS` entries for new immutable keys
- `AUT-XXXX` Update module docs (AI integration guide) with immutable key rationale

---

## (d) More Modular Code

### Current State — **PARTIALLY DONE**

**Backend services already modularising:**

```
backend/app/services/
├── advisor.py (1466 lines — MONOLITH)
├── advisor/                    # ← Already extracted subpackage
│   ├── __init__.py
│   ├── _common.py
│   ├── advisor_baseline.py
│   ├── dream.py
│   ├── finance.py
│   ├── replace.py
│   ├── upgrade.py
│   └── value.py
├── billing.py (536 lines)
├── fuel_feeds.py (741 lines)
├── iap.py (657 lines)
├── market_data.py
├── notify.py
├── backup.py (503 lines)
└── vector_search.py
```

**Advisor service (1466 lines)** is the largest monolith — but already has a parallel `advisor/` subpackage with extracted modules (value, replace, upgrade, finance, dream, _common). The main `advisor.py` appears to be a legacy facade.

**Other large files to decompose:**
- `backend/app/api/v1/social.py` (929 lines)
- `backend/app/api/v1/issues.py` (807 lines)
- `backend/app/api/v1/admin.py` (740 lines)
- `backend/app/services/fuel_feeds.py` (741 lines)
- `backend/app/services/iap.py` (657 lines)

### Target: Extract modules >500 lines into focused subpackages

| File | Lines | Extraction Plan |
|------|-------|-----------------|
| `backend/app/services/advisor.py` | 1466 | **Delete** — already replaced by `advisor/` subpackage; verify no imports remain |
| `backend/app/api/v1/social.py` | 929 | Split into `social/` subpackage: `posts.py`, `comments.py`, `reactions.py`, `feed.py` |
| `backend/app/api/v1/issues.py` | 807 | Split into `issues/` subpackage: `crud.py`, `blog.py`, `search.py` |
| `backend/app/api/v1/admin.py` | 740 | Split into `admin/` subpackage: `users.py`, `analytics.py`, `config.py`, `backup.py` |
| `backend/app/services/fuel_feeds.py` | 741 | Already has `fuel_feeds/` subdir? Check. If not, split: `nsw.py`, `vic.py`, `qld.py`, `sa.py`, `wa.py` |
| `backend/app/services/iap.py` | 657 | Split: `google.py`, `apple.py`, `verification.py`, `webhook.py` |

### Frontend Modularisation

Flutter frontend (`frontend/`) — 5 modules per AGENTS.md. Need to audit for:
- Large widget files → extract to `widgets/`
- Business logic in UI → move to `services/` or `bloc/`
- Shared theme/constants → centralise

### Child Issues to Create

- `AUT-XXXX` Remove legacy `backend/app/services/advisor.py` (verify zero imports)
- `AUT-XXXX` Split `backend/app/api/v1/social.py` into `social/` subpackage
- `AUT-XXXX` Split `backend/app/api/v1/issues.py` into `issues/` subpackage
- `AUT-XXXX` Split `backend/app/api/v1/admin.py` into `admin/` subpackage
- `AUT-XXXX` Split `backend/app/services/fuel_feeds.py` by state provider
- `AUT-XXXX` Split `backend/app/services/iap.py` by platform
- `AUT-XXXX` Audit Flutter frontend for large files (>500 lines) and extract

---

## (e) Rewrite/Refresh All Documentation

### Current State

**Repository docs (`docs/`):** 72 files across 14 directories. Good structure but many files stale.

| Section | Files | Status |
|---------|-------|--------|
| `docs/Engineering/` | 18 + ADRs | Architecture, AI models, API spec, container architecture — needs sync with current compose |
| `docs/Engineering/ai/` | 1 (`vector.md`) | Vector store schema — **good**, matches current implementation |
| `docs/Deployment-and-Infrastructure/` | 9 | Deployment guide, CI/CD, container consolidation migration — needs update for hosted stack changes |
| `docs/Security/` | 2 | Security policy, index — needs secret-file pattern doc (AUT-1533) |
| `docs/Testing-and-QA/` | 4 | Test strategy, QA logs — needs user testing process |
| `docs/Marketing-and-Website/` | 5 | Community garage, social image generation — needs mobile app split docs |
| `docs/Business-Reviews/` | 3 | Changelog, product rules — needs update |
| `docs/Finance/` | 5 | Fuel pricing, market data, payments — current |

**Outline wiki (AutoBrain collection):** Mirrors repo docs; sync needed.

**Missing/Stale Critical Docs:**
1. `container-consolidation-migration.md` — references old worker service; needs update for AUT-3153
2. `ai-router-integration.md` — needs `router_client.py`/`router_utils.py` architecture
3. `deterministic-first-ai.md` — **missing** — document the pattern for future modules
4. `secret-file-pattern.md` — **missing** — document AUT-1533 *_FILE pattern
5. `mobile-app-split.md` — **missing** — document `autobrain-mobile` repo creation
6. `vector-store-operations.md` — **missing** — operational guide for pgvector (backfill, reindex, model upgrade)

### Target: Full docs refresh + Outline sync

### Child Issues to Create

- `AUT-XXXX` Write `deterministic-first-ai.md` (pattern + router_utils reference)
- `AUT-XXXX` Write `secret-file-pattern.md` (AUT-1533)
- `AUT-XXXX` Update `container-consolidation-migration.md` for current hosted stack
- `AUT-XXXX` Write `ai-router-integration.md` (router_client + router_utils architecture)
- `AUT-XXXX` Write `vector-store-operations.md` (backfill, halfvec migration, model upgrade)
- `AUT-XXXX` Write `mobile-app-split.md` (autobrain-mobile repo creation guide)
- `AUT-XXXX` Sync all repo docs → Outline wiki (AutoBrain collection)
- `AUT-XXXX` Audit and update `deployment-guide.md` for EP5 specifics

---

## Summary of Child Issues to Create

| # | Title | Phase | Priority |
|---|-------|-------|----------|
| 1 | Merge market-data scraper into backend Celery (hosted) | 1a | high |
| 2 | Consolidate autobrain-backup + backup-agent into single backup service | 1a | high |
| 3 | Verify container count reduction end-to-end on EP5 | 1a | high |
| 4 | Add Redis caching for query embeddings in vector_search.py | 1b | medium |
| 5 | Evaluate halfvec migration for storage reduction (PoC) | 1b | medium |
| 6 | Add vector search weight tuning per entity type | 1b | medium |
| 7 | Document embedding model upgrade procedure | 1b | low |
| 8 | Add _AI_IMMUTABLE entries for diagnostics + service-prediction | 1c | high |
| 9 | Add corresponding _SCHEMAS entries for new immutable keys | 1c | high |
| 10 | Update AI integration docs with immutable key rationale | 1c | medium |
| 11 | Remove legacy backend/app/services/advisor.py (verify zero imports) | 1d | high |
| 12 | Split backend/app/api/v1/social.py into social/ subpackage | 1d | high |
| 13 | Split backend/app/api/v1/issues.py into issues/ subpackage | 1d | high |
| 14 | Split backend/app/api/v1/admin.py into admin/ subpackage | 1d | high |
| 15 | Split backend/app/services/fuel_feeds.py by state provider | 1d | medium |
| 16 | Split backend/app/services/iap.py by platform | 1d | medium |
| 17 | Audit Flutter frontend for large files (>500 lines) and extract | 1d | medium |
| 18 | Write deterministic-first-ai.md (pattern + router_utils reference) | 1e | high |
| 19 | Write secret-file-pattern.md (AUT-1533) | 1e | high |
| 20 | Update container-consolidation-migration.md for current hosted stack | 1e | high |
| 21 | Write ai-router-integration.md (router_client + router_utils architecture) | 1e | medium |
| 22 | Write vector-store-operations.md (backfill, halfvec, model upgrade) | 1e | medium |
| 23 | Write mobile-app-split.md (autobrain-mobile repo creation guide) | 1e | medium |
| 24 | Sync all repo docs → Outline wiki (AutoBrain collection) | 1e | high |
| 25 | Audit and update deployment-guide.md for EP5 specifics | 1e | high |

---

## Next Steps

1. **Immediate (this week):** Create child issues 1-3 (container consolidation) and 8-10 (AI immutable keys) — highest impact, lowest risk.
2. **Week 2:** Tackle modularisation (issues 11-17) — start with advisor.py removal (already has replacement).
3. **Week 3:** Vector optimisations (issues 4-7) and documentation (issues 18-25).
4. **Ongoing:** Verify each change on dev box → PR → auto-merge after QA+Security → deploy to EP5.

---

## Approval Request

This plan covers all 5 Phase 1 mandate areas. Requesting board confirmation to proceed with child issue creation and execution.

**Discord approval channel:** `#approvals`  
**Required:** One-line summary + exact ask  
**Ask:** "Approve Phase 1 improvement plan with 25 child issues; proceed with container consolidation (1a) and AI immutable keys (1c) first."

---

*Plan document — update via PUT /api/issues/{id}/documents/plan when Paperclip API recovers.*