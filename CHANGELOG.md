# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.


## [Unreleased]

### Fixed (AUT-2459)
- fix(backend): guard `GetFuelTypes` 404 in QLD DirectAPI v1.5 — country 21 (Australia) returns 404 for `GetFuelTypes`; the call is now wrapped in try/except so the rest of the QLD ingest path continues. `_parse_qld_direct_prices` uses a `P<id>` fallback label when the fuel type name is absent, ensuring prices are still recorded.

### Added (AUT-2459)
- test(backend): add `test_parse_qld_direct_prices_empty_fuel_map_uses_fallback_label` and `test_ingest_qld_fuel_prices_works_when_getfueltypes_404s` — unit tests asserting QLD ingest returns stations/prices even when `GetFuelTypes` is absent or 404.

## [0.3.280] - 2026-09-27

### Added (AUT-4120)
- feat(backend): Redis cache (TTL 1h) for query embeddings in `vector_search.py`; repeated searches return cached vector without 9Router call
- fix(backend): cached vectors are re-validated against `EMBEDDING_DIMENSION` on read; a poisoned/wrong-dimension cache entry is rejected and the router path re-derives the vector instead of binding it to SQL (22P02)

## [0.3.279] - 2026-09-26

### Fixed (AUT-3570)
- fix(frontend): wire CARTO_API_KEY into Servo Spy map tile URLs; embedded `?key=` param now passes the build-time `--dart-define=CARTO_API_KEY` value so CARTO basemaps render without watermark

## [0.3.278] - 2026-09-26

### Fixed (AUT-3979)
- fix(docker): remove orphaned top-level `volumes:` block left in `docker-compose.hosted.yml` by the AUT-3827 backup-agent removal, so the file has a single valid top-level `volumes:` key (duplicate keys are rejected by the Docker Compose strict YAML parser).
- fix(docker): drop the now-unused `/data/autobrain-backup/agent-data` bind mount. Merging it into `autobrain-backup` would have duplicated the `/backups` container path already served by `/data/autobrain-backup/data`, and the `backup-agent` service that owned that directory was removed.

## [0.3.277] - 2026-09-25
### Added (AUT-2631)
- feat(ios): define Fastlane release pipeline for TestFlight beta uploads and App Store releases. New `beta` and `release` lanes in `frontend/ios/fastlane/Fastfile` with `match` for cert/profile sync via S3, API key authentication, build number increment, and changelog integration.

## [0.3.276] - 2026-09-25

### Fixed (AUT-3049)
- fix(frontend): replace `withValues(alpha:)` with `withOpacity(alpha:)` in servo_spy_screen.dart for dart2js arm64 compatibility (PR #608)

## [0.3.275] - 2026-09-21

### Added (AUT-3661)
- feat(engineer): new engineer marketplace API with search/filter endpoints
  - GET `/api/v1/engineers/search` — geospatial search by postcode/radius, specialty multi-select, minimum rating, price range, availability window filters
  - GET `/api/v1/engineers/{id}` — engineer profile detail with reviews
  - Pagination and sorting by rating, distance, price
  - Backend: `Engineer` + `EngineerReview` models, pgvector embedding support for semantic search
  - Database migration: `a3661engineers_add_engineer_marketplace.py`

## [0.3.274] - 2026-09-18

### Fixed (AUT-3515)
- fix(advisor): create missing finance/dream/baseline modules to fix ModuleNotFoundError at startup; revert backend to working image and redeploy stacks

## [0.3.273] - 2026-09-18

### Fixed (AUT-3495)
- fix(frontend): fix Dart syntax error in vehicle_timeline_screen.dart

## [0.3.272] - 2026-09-18

### Fixed (AUT-3456)
- fix(frontend): wrap getCachedDecoded in try/catch to prevent indefinite spinner on web

## [0.3.271] - 2026-09-18

### Added (AUT-3447)
- feat(backend): WebAuthn passkey authentication — registration & authentication endpoints, DB schema, validation. Accepts credential creation options and verifies assertions. Endpoints: POST /api/v1/auth/passkey/register/begin, POST /api/v1/auth/passkey/register/complete, POST /api/v1/auth/passkey/authenticate/begin, POST /api/v1/auth/passkey/authenticate/complete, GET /api/v1/auth/passkey/list, DELETE /api/v1/auth/passkey/{credential_id}.

### Changed (AUT-3172)
- infra(ci): retire the standalone `autobrain-worker` image build (AUT-3153 follow-up). Removed the `worker` leg from every `for svc in backend worker ai frontend` loop in `.github/workflows/build-hosted.yml` (build, per-arch verify, manifest assembly, digest capture) and `.github/workflows/dockerhub-publish.yml` (amd64 build + manifest assembly), dropped the `WORKER_DIGEST` env + `worker=...` arg from the compose-pin step, and removed the `worker` pin from `scripts/update-compose-pins.py`. CI no longer publishes the unused multi-arch worker image. The `docker/worker/Dockerfile` stays on disk as a reference for the security-scan workflows; `infra/k8s/worker.yaml` already runs the Celery worker+beat from `autobrain-backend:latest` and is unchanged.

### Fixed (AUT-3189)
- infra(env): declare `FUEL_SA_API_KEY` and `FUEL_SA_ENABLED` in `.env.example` so hosted operators can provision the SA SAFPIS feed referenced by `docker-compose.hosted.yml`.

## [0.3.270] - 2026-09-17

### Fixed (AUT-1805)
- fix(ci): add job-level `timeout-minutes: 15` to the `ocr-review` job in `.github/workflows/code-review.yml` so a 9Router stall or runner hang can never hold the x64 runner beyond 15 min (previously unbounded at job level). The step-level 10 min timeout remains as the inner guard.

## [0.3.269] - 2026-09-17

### Added (AUT-1872)
- feat(deploy): upgrade script + hardened hosted compose. `scripts/upgrade-instances.sh` redeploys Portainer stacks tier-by-tier (Demo → Default → Hosted) with explicit image pulls and health gates. `docker-compose.hosted.yml` drops dead `dongle-server` + duplicate `hub`, uses `:-` defaults for `POSTGRES_USER`/`POSTGRES_DB` and `DONGLE_SERVER_URL` so Portainer redeploys survive empty-stack env. PR #375.

## [0.3.268] - 2026-09-16

### Fixed (AUT-3039)
- fix(test): fix `pumpAndSettle` timeout in desktop layout visual regression tests by mocking `getCachedDecoded` in `_FakeApi`, setting `_loading = false` in `VehicleListScreen._load()`, and correcting test assertions. The visual regression workflow (desktop 1280/1440/1920) now passes.

## [0.3.267] - 2026-09-15

### Fixed (AUT-3080)
- fix(security): restrict CORS `allow_methods` to explicit set (GET/POST/PATCH/DELETE) and `allow_headers` to narrow list (Authorization, Content-Type, Accept, X-Requested-With). Add startup validator rejecting `CORS_ALLOWED_ORIGINS=["*"]` with `allow_credentials=True`.
