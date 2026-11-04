# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.

## [Unreleased]
### Added (AUT-3990)
- feat(backend): add resale valuation endpoints (AUT-3990)

### Added (AUT-6645)
- feat(ai): per-module AI confidence floors with env override; default raised from 0.75 to 0.85 (AUT-6645)
- feat(ai): cost tracking endpoints `/v1/cost` and `/v1/cost/reset` for AI gateway (AUT-6646)
- docs: update router validation tests for new confidence floor behavior

### Added (AUT-6519)
- docs: add secret-file-pattern.md documenting AUT-1533 *_FILE secret injection pattern for docker-compose (AUT-6519)

### Fixed (AUT-6431)
- fix(build): add archive dependency override to fix Dart compile failure (AUT-6431)

### Fixed (AUT-6456)
- fix(ci): the `pytest` job in `ci-tests.yml` had no PostgreSQL service container, so the full backend test suite died with `ConnectionRefusedError: [Errno 111] Connect call failed (127.0.0.1, 5432)` (e.g. `tests/test_logbook_club_reg.py::test_club_reg_logbook_is_disabled`). Adds a `pgvector/pgvector:pg17` service (same image as the `alembic-migrations` job) to the `pytest` job, exposing `localhost:5432` with `autobrain`/`autobrain`/`autobrain` credentials matching the suite's `DATABASE_URL`.

### Added/Changed (AUT-3533)
- fix: Servo Spy map blank white screen on hosted by resolving undefined _kCartoKeyParam and injecting CARTO API key (PR #715)

### Fixed (AUT-5612)
- `devices.vehicle_type` rollback data loss: `aut5092_dev_veh_type` is a no-op
  on the hosted `create_all` database it exists to repair (the column is already
  there), yet its `downgrade()` dropped the column anyway, destroying real data
  on rollback. `upgrade()` now stamps the column it adds with a provenance
  marker (`COMMENT ON COLUMN`) and `downgrade()` drops only a column carrying
  that marker — a pre-existing column is left alone, while a genuine rollback of
  a column this revision created still drops it. Covered by
  `tests/test_alembic_heads.py` (offline) and two new cases in
  `tests/test_alembic_migration_only.py` (real Postgres, `alembic-migrations` CI
  job).
- `BACKUP_OFFSITE_INGEST_KEY`'s docstring still said `/api/backup/ingest`, an
  endpoint that 404s; the value is the `X-Ingest-Key` for `/ingest`.

### Changed (AUT-6127)
- Security: update dev egress IP for hosted firewall (`fw-keeper`) from `122.199.30.128` to `103.232.252.9` in `docker-compose.hosted.yml` comments and `docs/Security/security.md`. The `fw-keeper` container on the Oracle VM (152.69.188.133) must be updated via Portainer to allow the new IP for Portainer agent (`:9001`) and 9Router (`:20128`) access.

### Removed (AUT-5718)
- Removed the dead `POST /api/v1/ci/webhook` CI triage receiver. The GitHub Actions `ci-triage-webhook.yml` fire job has never posted to the AutoBrain backend — it fires `secrets.CI_TRIAGE_WEBHOOK_URL`, the Paperclip routine trigger on the `CI Triage` routine, and that routine trigger is the only thing that wakes the CI Triage Agent. The backend route had no callers: AutoBrain-Hosted answered `503 CI triage webhook not configured` to every request since at least 2026-09-03 because `docker-compose.hosted.yml` wired `CI_TRIAGE_*` + server-side `PAPERCLIP_*` settings in `backend/app/core/config.py`, the same block in `docker-compose.hosted.yml`, the `CI_TRIAGE_*` block in `.env.example`, and the `/ci/webhook` row in `docs/Engineering/api-spec.md`; `ci-triage-webhook.yml` and the deployment guide now state that the Paperclip routine trigger is the canonical receiver so the route is not re-added or repointed. The Hosted stack no longer needs `PAPERCLIP_API_KEY`/`CI_TRIAGE_WEBHOOK_SECRET` to boot. `backend/tests/test_ci_receiver_removed_aut5718.py` asserts the route is gone (404) and the settings no longer exist, so a re-added receiver fails CI.

### Added (AUT-3512)
- feat(backend): extend pgvector embeddings to `fuel_price_snapshots`, `devices`, `market_listing_cache`, and `vehicles` tables with HNSW indexes. New Alembic migration `g7h8i9j0k1l3` adds `embedding vector(1536)` columns and cosine-similarity indexes. Search service `_ENTITY_MAP` expanded with `fuel_price`, `device`, `market_listing`, `vehicle` entity types (including `scope_field` override for vehicle-scoped search). Vector embedding service `_to_text` updated for new types. API `/api/v1/search` entity_types description updated.

### Fixed (AUT-1605)
- fix(ai): rate limiter now evicts stale entries on overflow instead of clearing all state, preventing rotating-IP attackers from resetting limits for all clients (PR #274)

## [0.3.312] - 2026-11-04
### Changed
- Bump version to 0.3.312

## [0.3.311] - 2026-11-04
### Changed
- Bump version to 0.3.311

## [0.3.310] - 2026-11-03
### Changed
- Bump version to 0.3.310

