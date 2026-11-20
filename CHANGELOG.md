# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.

## [Unreleased]

<<<<<<< ours
## [0.3.321] - 2026-11-19
=======
### Fixed (AUT-226)
- fix(test): `tests/test_advisor_upgrade.py` mocked the async `get_accessible_vehicle` with a sync lambda, causing "object types.SimpleNamespace can't be used in await expression" during the advisor upgrade route test. Use `AsyncMock(return_value=fake_vehicle)` so the await expression resolves correctly. Backend pytest suite no longer fails at this test.
- fix(test): `tests/test_aut207_token_lifecycle.py`, `tests/test_aut3447_passkey.py`, `tests/test_logbook_club_reg.py`, `tests/test_odometer_priority.py`, `tests/test_trip_gps.py` used `asyncio.run(init_db())` in module-scoped fixtures, which created a separate event loop conflicting with pytest-asyncio's session-scoped loop and caused "Future attached to a different loop" flakiness in the full pytest suite. Changed to `@pytest_asyncio.fixture(scope="module", autouse=True, loop_scope="session")` with `await init_db()` so all tests share the session loop.
- fix(alembic): migrations `g7h8i9j0k1l2` and `g7h8i9j0k1l3` (pgvector embedding columns) were not idempotent — `init_db()` (create_all) creates the columns first, then `alembic upgrade head` fails with "column already exists" on the test DB built by `test_hosted_shaped_database_reaches_head`. Changed `ALTER TABLE ... ADD COLUMN` to `ADD COLUMN IF NOT EXISTS` so migrations survive create_all-first test runs.

## [0.3.318] - 2026-11-11

### Fixed (AUT-448)
- fix(frontend): `FlutterSecureStorage` constructor now maps `webOptions: _webOptions` and `wOptions: _winOptions` separately instead of assigning a `WebOptions` value to the `wOptions` (WindowsOptions) parameter, which blocked the frontend Docker image build (PR #1116)

## [0.3.317] - 2026-11-11

### Fixed (AUT-226)
- fix(alembic): repair dangling `f7e8d9c0b1a2` down_revision (`m3rge07` → `m3rge06`) and unify all alembic heads in `m3rge08` (`a3661engineers`, `aut3447_passkey_credentials`, `aut5092_dev_veh_type`, `g7h8i9j0k1l3`) so `alembic upgrade head` resolves to a single head (PR #1113)

## [0.3.316] - 2026-11-09
### Fixed (AUT-380)
- fix(alembic): merge migration heads `aut5092_dev_veh_type` + `g7h8i9j0k1l3` via `m3rge08`; remove duplicate `m3rge07` revision; `alembic upgrade head` now resolves to single head (PR #1110)

## [0.3.315] - 2026-11-09

### Fixed (AUT-226)
- fix(backend): resolve duplicate alembic merge revision m3rge07; add m3rge08 merge to unify pgvector embedding chain with device vehicle_type repair chain (AUT-226)
- fix(test): use AsyncMock for async get_accessible_vehicle in advisor upgrade route test (AUT-226)
- fix(test): add PostgreSQL service to pytest job for full backend suite (AUT-6456)

### Fixed (AUT-374)
- fix(alembic): idempotent pgvector embedding column/index creation; handles hosted `create_all` pre-creating columns as text (AUT-374)
- fix(alembic): merge heads m3rge07 (engineers+passkey) and m3rge08 (embedding chain) to restore single-head alembic upgrade path (AUT-374)
- test: add async fixture for passkey token lifecycle tests

### Added (AUT-322)
- chore(mobile): mobile release v0.3.311+253 — `release-mobile.yml` `promote_to_production` flag now promotes the closed-testing release to Google Play production (staged rollout 10% → 50% → 100%); shared changelog entry for mobile GitHub Release (AUT-322)

## [0.3.314] - 2026-11-09
### Added (AUT-6415)
- feat(docker): merge dongle-server + backup GUI into backend container (AUT-6415)

## [0.3.313] - 2026-11-06
### Changed (AUT-217)
- refactor(phase1d): split social.py + issues.py into subpackages, remove legacy advisor.py (PR #992)
- fix(ci): add CHANGELOG.md entry for phase1d-modularize-services PR to satisfy changelog gate (AUT-217)

## [0.3.312] - 2026-11-04
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
- Removed the dead `POST /api/v1/ci/webhook` CI triage receiver. The GitHub Actions `ci-triage-webhook.yml` fire job has never posted to the AutoBrain backend — it fires `secrets.CI_TRIAGE_WEBHOOK_URL`, the Paperclip routine trigger on the `CI Triage` routine, and that routine trigger is the only thing that wakes the CI Triage Agent. The backend route had no callers: AutoBrain-Hosted answered `503 CI triage webhook not configured` to every request since at least 2026-09-03 because `docker-compose.hosted.yml` wired `CI_TRIAGE_WEBHOOK_SECRET`/`CI_TRIAGE_PARENT_ISSUE_ID`/`CI_TRIAGE_GOAL_ID` to empty defaults the Hosted env file never set, and the Hosted access log contains no POST from any Actions runner to that path. Deletes `backend/app/api/v1/ci.py`, its router registration, the `CI_TRIAGE_*` + server-side `PAPERCLIP_*` settings in `backend/app/core/config.py`, the same block in `docker-compose.hosted.yml`, the `CI_TRIAGE_*` block in `.env.example`, and the `/ci/webhook` row in `docs/Engineering/api-spec.md`; `ci-triage-webhook.yml` and the deployment guide now state that the Paperclip routine trigger is the canonical receiver so the route is not re-added or repointed. The Hosted stack no longer needs `PAPERCLIP_API_KEY`/`CI_TRIAGE_WEBHOOK_SECRET` to boot. `backend/tests/test_ci_receiver_removed_aut5718.py` asserts the route is gone (404) and the settings no longer exist, so a re-added receiver fails CI.

### Added (AUT-3512)
- feat(backend): extend pgvector embeddings to `fuel_price_snapshots`, `devices`, `market_listing_cache`, and `vehicles` tables with HNSW indexes. New Alembic migration `g7h8i9j0k1l3` adds `embedding vector(1536)` columns and cosine-similarity indexes. Search service `_ENTITY_MAP` expanded with `fuel_price`, `device`, `market_listing`, `vehicle` entity types (including `scope_field` override for vehicle-scoped search). Vector embedding service `_to_text` updated for new types. API `/api/v1/search` entity_types description updated.

### Fixed (AUT-4812)
- fix(backend): `tests/test_advisor_value.py` could not import `BAND_LOW_RATIO` / `BAND_HIGH_RATIO` from `app.services.advisor`, so the entire backend suite failed at collection — masked by `ci-tests.yml` running the suite as `pytest … || true`. The `app.services.advisor` package `__init__.py` already re-exports both constants from `advisor/value.py`; the stale `backend/app/services/advisor.py` module that shadowed the package is deleted (no imports referenced it). Removed `|| true` from the full-suite step in `.github/workflows/ci-tests.yml` so future collection errors fail the build. All 16 `test_advisor_value.py` tests pass; full suite collects without import errors.

### Fixed (AUT-5668)
- fix(ci): `ci-triage-webhook.yml` fire job was incorrectly pinned to the self-hosted vm2 runner (`runs-on: [self-hosted, linux, x64, vm2]`) despite comments explicitly stating it must run on `ubuntu-latest` to avoid consuming scarce self-hosted runners for 15-minute sleep+curl bursts. The misconfiguration caused the step to hang and be killed by the 20-minute timeout (AUT-5668), silently losing ~half of CI triage wakes. Changed `runs-on` to `ubuntu-latest` (timeout was already increased to 30 minutes).

### Fixed (AUT-5584)
- fix(frontend): `Sync mobile app` workflow failed on `main` with `lib/core/models/fuel_history.dart is not referenced by a part directive in lib/core/models.dart`. The monorepo `frontend/lib/core/models.dart` was missing the `part 'models/fuel_history.dart';` directive that `autobrain-mobile` PR #60 added to its models.dart. Added the missing `part` directive and the corresponding `fuel_history.dart` model file to the monorepo source-of-truth so the sync guard (AUT-5205) passes and the mobile tree stays in parity. Verified by re-running the `Sync mobile app` workflow.

### Security (AUT-4726)
- fix(ci): wire `backend/tests/test_deps_transitive_cves.py` into the required
  `Backend — pytest smoke` CI job so transitive dependency CVE pins (starlette,
  PyJWT, python-jose/ecdsa) are enforced on every PR and push. The guard runs
  offline (reads `requirements.txt` only), needs no database, and blocks merges
  when pins fall below the fixed floors (starlette ≥1.3.1, PyJWT ≥2.15.0,
  no python-jose/ecdsa).

### Fixed (AUT-5936)
- fix(frontend): `favourite_stations_screen.dart` referenced `FuelPriceWatchlist` without importing `core/models.dart`, causing a compile error (`Type 'FuelPriceWatchlist' not found`) that failed the visual-regression CI on branches `fix/aut-5920-pr-based-pin-bumps` and `AUT-4556-servo-saver-map-improvements`. Added the missing import.

### Changed (AUT-4556)
- feat(frontend): servo-spy map improvements — removed the distance slider, added station clustering (nearby stations grouped on the map), and added a Favourites tab to view saved fuel stations.

### Fixed (AUT-5846)
- fix(backend): removed unmaintained `passlib[bcrypt]==1.7.4` from `backend/requirements.txt` and migrated `backend/app/core/security.py` to use `bcrypt` directly (`bcrypt.hashpw` / `bcrypt.checkpw`). passlib 1.7.4 (2020) is the last release and its bcrypt backend has known correctness issues (truncation bugs, version detection). The direct bcrypt API is already pinned (`bcrypt==4.0.1`) and is the OWASP-recommended algorithm. Regression test `tests/test_api.py::test_password_hashing` verifies hash/verify round-trip and wrong-password rejection; full `pytest tests/test_api.py` passes (17/17).

### Fixed (AUT-5777)
- fix(nginx): `/docs`, `/openapi.json`, and `/redoc` returned the Flutter SPA shell (200 text/html) instead of the FastAPI documentation on hosted. The frontend nginx catch-all `location /` served index.html for these paths because explicit proxy blocks were missing. Adds `location /docs`, `location = /openapi.json`, and `location /redoc` blocks in `docker/frontend/nginx.conf` that proxy to `backend:8000`. Also enables `docs_url="/docs"` and `redoc_url="/redoc"` in `backend/app/main.py` for all environments (was gated off in production). Verified post-deploy: hosted.autobrainservice.app/docs, /openapi.json, and /redoc now serve Swagger UI, OpenAPI JSON, and ReDoc respectively.

### Fixed (AUT-5584, AUT-4772)
- fix(mobile-sync): reverted `autobrain-mobile` PR #60, which red-lined `Sync mobile app` on `main` (run 37212706670) with `lib/core/models/fuel_history.dart is not referenced by a part directive in lib/core/models.dart`. #60 added a **mobile-only** 30-day Servo Spy station price chart (model file `lib/core/models/fuel_history.dart` + an inline chart in `lib/screens/servo_spy/servo_spy_screen.dart`). `sync-mobile.sh` copies `frontend/lib/` verbatim over the mobile tree, so every sync overwrote the mobile `models.dart` and the chart source, orphaning the model file on disk and tripping the AUT-5205 part-directive guard. The same chart already ships in the shared lineage: `frontend/lib/screens/servo_spy/servo_spy_station_history_screen.dart` (AUT-2376) renders it from `FuelPricesApi.stationHistory` and converts cents to dollars on both the axis and the tooltip, so the duplicate only cost the cents-vs-dollars bug tracked as AUT-4772. Store app keeps the chart through the synced `ServoSpyStationHistoryScreen`.

### Fixed (AUT-5306)
- docker(backend): merged `origin/main` into `feat/AUT-4113-market-data-celery` (PR #777), resolving the `docker/backend/Dockerfile` conflict — keeps AUT-4718's `python:3.13.16-slim-trixie@sha256:6906dca8…` base repin (clears the `image-scan` HIGH/CRITICAL findings from the stale 3.13.15 digest) together with AUT-3843's Playwright Chromium layer (`ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` after the backend `pip install`, `chown -R autobrain:autobrain /ms-playwright`, and the chrome-sandbox re-SUID gate).
### Changed (AUT-5654)
- ci: moved the last four GitHub-hosted jobs onto the self-hosted vm2 runners, finishing this repo's hosted-runner migration. `visual_regression.yml` (was `ubuntu-latest`) now runs on `[self-hosted, linux, x64, vm2]`; its `subosito/flutter-action@v2` step downloads the Flutter SDK itself, so no pre-installed toolchain is required on the runner. `dockerhub-publish.yml`'s `dedupe-main-queue`, `ci-queue-guard.yml`'s `cancel-orphaned-runs`, and `ci-triage-webhook.yml`'s `fire` also move to `[self-hosted, linux, x64, vm2]`: all three are API-only gates that call `gh api` to cancel superseded/orphaned runs and to fire the triage webhook, and none of them checks out or executes repository code, so they are safe on a persistent runner even under the `pull_request` trigger. `build-hosted.yml`'s matrix already resolved to vm2/ARM64 and is unchanged. After this, no workflow in this repo requests a GitHub-hosted runner.

### Fixed (AUT-5714)
- deploy(infra): hardened the single self-hosted ARM64 runner (`gh-runner-autobrain-arm64`, Oracle VM, Portainer EP5 stack 123) against the GitHub Actions broker WebSocket drops logged as `System.Net.Sockets.SocketException (125): Operation canceled`, and gave its stack a git source of truth for the first time. Measured 2026-09-27..2026-10-05 from the EP5 container logs: 86 drop events (~9/day), 76 of them while idle, every one self-healing via a ~12s broker backoff + session restart — 62 jobs started, 62 succeeded, 0 cancelled, 0 failed, `RestartCount=0`. The drop itself is upstream broker behaviour (the runner client cancels its own long-poll), so the hardening is container-level: `stop_grace_period: 30m` (Docker's 10s default SIGKILLs the runner mid-build on any stop/redeploy, and a drop overlapping a redeploy could previously compound into a lost job — now the update waits for the build to drain), the image digest-pinned to the arm64 manifest EP5 runs (v2.337.0) instead of floating `:latest`, and `DISABLE_AUTO_UPDATE=true` (an in-place self-update silently drifted the running broker build off whatever digest was pinned — a pin nothing enforced). Adds `docker-compose.runner.hosted.yml` as the only definition of the stack (it previously existed only inside Portainer, so every change was an untracked hand-edit) and `scripts/check-runner-compose.py` as a structural guard wired into `compose-checks.yml` — it fails on the previous live definition (floating tag, auto-update on, no grace period) and passes on the hardened one. Applied to EP5 stack 123; the runner stays `online` with a fresh listener session and the keepalive canary (`arm64-runner-keepalive.yml`, AUT-5463) continues to pass.

### Fixed (AUT-5522)
- fix(nginx): the AUT-5460 fix merged as `08a5fb29` was **inert on hosted** — it trusted only Cloudflare's published edge ranges, but the frontend container's immediate TCP peer is the local reverse proxy (the `nginx-proxy-manager` container on the same docker bridge; measured live in PR #901: `redis-cli --scan --pattern 'login:fail:*'` returned only `login:fail:ip:172.18.0.3`), never a Cloudflare edge. `real_ip_header` only rewrites `$remote_addr` for peers in `set_real_ip_from`, so no request was ever rewritten, every visitor on the internet kept sharing one `login:fail:ip:172.18.0.3` key (`LOGIN_MAX_ATTEMPTS=5`, `LOGIN_WINDOW_SECONDS=3h`), and five failed logins by anyone still locked out every hosted customer for three hours. `docker/frontend/nginx.conf` now also trusts the docker bridge pool the proxy hops over (`172.16.0.0/12`, covering hosted npm `172.18.0.3` and the EP2 host nginx `172.26.0.1`) alongside Cloudflare's full published edge set — which adds the one missing range `198.41.128.0/17` (Cloudflare publishes 15 IPv4 ranges; the list carried 14). A public client cannot reach the container with a `172.16/12` source address (the compose files bind the frontend to `127.0.0.1` on hosted/dev and DNAT preserves an external source IP), so the AUT-303 spoof bypass stays closed; the residual widening is that a co-tenant container on the same bridge could set `X-Real-IP`. `docker/frontend/nginx-proxy.conf` is **deleted** — no Dockerfile, compose file or script referenced it (only the changelog and its own test did), so it was a second copy of the trust boundary that future edits would change nothing about. `/api/` now sends `X-Forwarded-For $remote_addr` instead of `$proxy_add_x_forwarded_for`, so a client-supplied chain is never re-attached (nothing reads XFF today — `client_ip()` ignores it — so this is defence in depth). Deliberately **no** backend change: `client_ip()` still trusts only the proxy-set `X-Real-IP` and the socket peer. `backend/tests/test_aut5460_cf_real_ip.py` now pins the trust boundary **in both directions**: a stale list fails (this is how `198.41.128.0/17` shipped), an over-broad edit such as `set_real_ip_from 0.0.0.0/0;` or a bare RFC1918 range fails, and a missing `172.16.0.0/12` fails — the last is the regression that made `08a5fb29` inert. Verified locally: 10 passed; the four new/updated pins all **fail** against the merged `08a5fb29` conf, and injecting `set_real_ip_from 0.0.0.0/0;` into the fixed conf fails only the allowlist pin. `nginx -t` was **not** run by the authoring box (no docker/nginx there) — run it on the dev box before deploy. After deploy, the acceptance check is the same probe that found the bug: `redis-cli --scan --pattern 'login:fail:*'` must show per-visitor public addresses, never `172.1x.x.x`.

### Fixed (AUT-5639)
- fix(backend): `GET /api/v1/advisor/replace` 500ed for every caller, and the next build of the backend could not boot at all. AUT-3916 (`389213ca`, Sep 26) deleted the legacy `backend/app/services/advisor.py` — which held `compute_replace` — and rewired `app/api/v1/advisor.py` to import it from the new `app.services.advisor` package, but the function was never moved into the package, so the package never exported it. The 500 stayed invisible for ~9 days because `ci-tests.yml` runs the suite as `pytest … || true` and `tests/test_advisor_replace.py` skips its route tests when `app.main` fails to import (they had never actually run: the module's fake vehicle had no `id` and `get_accessible_vehicle` was patched with a sync lambda, both now fixed). AUT-5639's PR #915 added the missing import line, which turned the latent breakage into a hard `ImportError` at boot for every process that imports `app.main` — i.e. main went red and any image built from it would crash-loop. This restores `compute_replace` in `app/services/advisor/replace.py` (verbatim from the deleted legacy module — deterministic, no AI/no network: used cost = current private-sale mid, new cost = mid × documented `new_used_premium(age)`, gap = replacement − current − trade-in mid, `surplus` on a non-positive gap) and re-exports it from `app/services/advisor/__init__.py`. `tests/test_advisor_replace.py` now runs instead of skipping (15 passed, 0 skipped; 834 tests collect clean) and pins the export with a new `test_compute_replace_is_exported`, so a future dropped export fails collection at CI time instead of in production.
### Fixed (AUT-5132)
- fix(deploy): the nightly hosted deploy to EP5 stack 122 was a **silent
  no-op**. Stack 122 is an inline Portainer stack (`GitConfig: null`) with
  every image digest-pinned, so `pullImage: true` re-resolves an immutable
  digest and can never move a pin; and the compose-pin sync step in
  `build-hosted.yml` was gated on a *digest* having changed, so a
  compose-only edit (the #870 `alembic` pre-step) never reached the stack
  even though the diff looked correct. `scripts/sync-compose-to-portainer.py`
  now asserts, after every sync and on a read-only `--verify-only` pass, that
  each running container's `RepoDigests` (`/images/{id}/json`) contains the
  digest this compose pins and that its `command`/`entrypoint` matches what the
  compose declares — interpolated against the stack env first, because compose
  interpolates before the value reaches the container. A HTTP 200 from
  Portainer is no longer treated as evidence that the change shipped; drift
  exits 7. The sync step's `changed` gate is replaced by
  `always() && steps.bump.outcome == 'success'`. Covered by 28 tests in
  `scripts/test_sync_compose_to_portainer.py` and documented in
  `docs/Deployment-and-Infrastructure/deployment-guide.md`
  ("Stack 122 (`autobrain-hosted`) is an INLINE, digest-pinned stack").

### Fixed (AUT-5063)
- fix(security): depublish the last surviving copy of the compromised demo credential literal. `docker-compose.demo.yml:2` (added by AUT-5582, after the AUT-5063 sweep was scoped) still carried the published `demo@autobrainservice.app / demo` pair in its header comment, so the file that defines the Demo tier re-leaked the exact secret AUT-5063 removed from the other nine sites. The comment now points at the Paperclip secret `demo/demo-account-password` instead. Also wires `DEMO_PASSWORD` into the Demo backend's environment as a **required** var (`${DEMO_PASSWORD:?…}`, matching the existing `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` pattern in the same file): `DEMO_MODE: "true"` was already set but no password was passed, so after AUT-5063's fail-closed seeding landed, reviving the Demo stack would have booted healthy and silently refused to create the demo account (and `check_demo_compose.py` — which asserts every `${VAR}` resolves — would have rejected the file anyway). Now the stack fails closed at deploy time rather than at seed time. No redeploy: AUT-2409 keeps deploys hosted-only and the Demo stack is down (AUT-5057).
### Fixed (AUT-5137)
- fix(backend): `app.db.bootstrap` failed open on a failed `alembic upgrade` — it caught *every* migration error and degraded to `Base.metadata.create_all`, which never alters an existing table. So a migration that only adds a column (or any bad DDL, permission error, truncation, stale revision id, or forked head) silently did nothing while boot proceeded and the deploy reported success — schema drift surfacing hours later as an application error far from the deploy. This is the class behind the hosted `devices.vehicle_type` miss (AUT-5122, a `StringDataRightTruncationError` stamping a 34-char id into `varchar(32)` meant the repair never applied) and the AUT-4925 head fork in AUT-5114; both were swallowed by the one `except`. The fallback is now scoped to a genuinely fresh database (`information_schema` reports zero tables in `public`, i.e. an un-stamped schema with nothing to drift from); every other failure aborts startup. Before aborting, bootstrap emits a structured `migration_failed_startup_aborted` error log line and POSTs the same payload to a new optional `BOOT_ALERT_WEBHOOK_URL` ops webhook (best-effort, 5s timeout, never raises, so alerting can never mask the abort). A database whose state cannot be inspected at all also fails closed rather than guessing. Because the container command is `sh -c '… && python -m app.db.bootstrap && …'`, the raise now exits the container instead of handing a healthy-looking boot to uvicorn — this is a deliberate behaviour change: a broken migration will now crash-loop the backend instead of serving traffic against a drifted schema, which is the point. Regression tests in `backend/tests/test_aut5137_bootstrap_fail_closed.py` drive the alembic CLI seam and the engine seam (no live postgres needed) and **fail on the pre-fix code** with `DID NOT RAISE`; they cover abort-on-non-empty-db (plus the log line, the alert, and both `head`/`heads` attempts), the still-working fresh-database `create_all` fallback, fail-closed on an uninspectable database, and that a clean upgrade never probes the schema at all.
### Fixed (AUT-5639)
- fix(backend): `GET /api/v1/advisor/replace` returned HTTP 500 for every caller. The route body calls `compute_replace(db, vehicle, odometer_km=..., horizon_months=...)`, but `app/api/v1/advisor.py` never imported that name — the module import block has listed `compute_advisor_recommendation, compute_dream, compute_finance_plan, compute_market_value, compute_upgrade, find_comparables, trade_in_band` since the module landed in AUT-2446 (`c858155`, #489), so the Replace module has been unreachable since it shipped. `ruff check --select F821` reports exactly this one undefined name in the module and nothing else. Adds `compute_replace` to the `from app.services.advisor import (...)` block. `tests/test_advisor_replace.py` was already asserting the route envelope and had been failing for the same reason, masked by `ci-tests.yml` running the suite as `pytest … || true` — it is green now (12 passed, 2 skipped). Surfaced while verifying the AUT-5137 bootstrap PR, where the newly strict test collection made this pre-existing failure visible.

### Added (AUT-5611)
- deploy: the Default tier on Portainer endpoint 2 ran as three hand-made containers with no compose definition anywhere in the repo (`ai` on a floating `:latest-amd64`, `backend` tag-pinned to `0.3.308` but with zero network aliases and no compose labels, `frontend` on a floating `:default`), so nothing stack-driven could redeploy it — `scripts/upgrade-instances.sh` resolved the tier by a Portainer stack named `autobrain`, which did not exist, and the Default step of the promotion chain failed silently, while Watchtower (nightly 04:00 AEST, all containers) recreated them outside any redeploy path. Adds `docker-compose.default.yml` as the tier's only definition (all three images digest-pinned to the digests EP2 was already running, `restart: unless-stopped`, `autobrain_default` joined as an external network with explicit `ai`/`backend`/`frontend` aliases) and adds `scripts/check-default-compose.py` as a structural guard wired into `compose-checks.yml`. Deployed as Portainer stack `autobrain-default` (id 137) with zero image drift; `default.autobrainservice.app/health` returns 200.

### Added (AUT-5582)
- deploy: the Demo tier on Portainer endpoint 2 ran as six hand-made containers with no compose file anywhere on the host and no Portainer stack, so every redeploy was an archaeology exercise and a hand-recreate silently lost the compose DNS aliases — backend could not resolve postgres/redis/minio and frontend nginx could not resolve backend, i.e. 502 on every proxied path. Adds `docker-compose.demo.yml` as the tier's only definition (project name pinned to `autobrain-demo` so the existing volumes and the `autobrain-demo_default` network the `plate-api-scraper` stack joins are reused; all six images digest-pinned to the ImageIDs EP2 actually runs, so the recreate changed nothing), `sync-compose-to-portainer.py --create --env-file` (Portainer 2.39 has no JSON stack-create route, so creation posts the multipart form the UI posts to `/stacks/create/standalone/file`), and `check_demo_compose.py` as a deployability gate (every `${VAR}` resolves, digest pins, project name, volume names, no literal secrets) since no docker CLI can reach EP2 to run `compose config`. Deployed as Portainer stack `autobrain-demo` (id 136), all six services healthy with aliases restored.

### Fixed (AUT-5356)
- test(backend): three test modules had been failing at **import** for an unknown number of releases and the coverage they were written for silently never ran — `ci-tests.yml` runs the suite as `pytest … || true`, so a collection error could not fail the build. `tests/test_advisor_value.py` imported `BAND_LOW_RATIO` / `BAND_HIGH_RATIO` / `TRADE_IN_*_RATIO` / `_CONDITION_MULTIPLIER` from `app.services.advisor`, but the AUT-4812 package split moved them into `advisor/value.py` without re-exporting them (also AUT-4812); the package `__init__` now re-exports all six, matching its own "all public names are re-exported" contract. `tests/test_aut2381_arbitration.py` tested an arbitration design that no longer exists (`SourceTrust` / `PriceCandidate` / `_consistency_bonus` / `select_best_price`) — AUT-2386 moved the rule to `app/services/fuel_source_arbitration.py` with authority-dominant scoring and a median spread penalty, so the suite is rewritten against the surviving behaviour (authority ordering, freshness window with naive-timestamp and clock-skew handling, spread penalty, `arbitrate()` determinism, empty input raising). `tests/test_car_check.py` tested `parse_listing_url` / `_verdict` / `_band`, all removed by AUT-2651, and is rewritten against the current scoring helpers, flag builders and the `car_check_fallback` / `validate_car_check_response` contract. `test_advisor_value.py`'s route test monkeypatched the awaited `get_accessible_vehicle` with a sync lambda (surfaced only now that the module collects) and built a vehicle stub without `id`. `pytest --collect-only -q` in `backend/` now exits 0 (825 collected), and `ci-tests.yml` gains a dedicated collect-only step so a future import error fails the build instead of being swallowed by the full suite's `|| true`. No production behaviour change outside the added re-exports.

### Changed (AUT-5356)
- ci(backend): `aiosqlite==0.21.0` added to `backend/requirements.txt` (test/dev block, next to `pytest` / `pytest-asyncio` / `ruff`). Four test modules — `tests/test_backup_completeness.py`, `tests/test_demo_fuel_seed.py`, `tests/test_seed_reset_demo.py`, `tests_social/test_social.py` — build a `sqlite+aiosqlite` async engine at import time, and the AUT-5356 collect-only gate turned their `ModuleNotFoundError: No module named 'aiosqlite'` into a hard CI failure on every push and PR (main went red on `d005e8ce`). With the driver present, `pytest --collect-only -q` collects 829 tests with zero errors. No runtime behaviour change; the test/dev block already ships in the backend image. Verified locally: collection clean, the AUT-5137 fail-closed tests pass (4/4), `test_alembic_heads.py` passes (4/4), and the two fail-closed regression tests fail on pre-fix `main` as intended. OSV reports no advisories for `aiosqlite==0.21.0`.

### Fixed (AUT-5460)
- fix(nginx): a customer's first login attempt could return `429 Too many failed login attempts` instead of `401` — behind Cloudflare, nginx's `$remote_addr` is the Cloudflare **edge** IP, so the `X-Real-IP` header the frontend proxy set was the edge IP and every visitor on that edge node shared one `login:fail:ip:<edge>` bucket (`LOGIN_MAX_ATTEMPTS=5`, `LOGIN_WINDOW_SECONDS=3h`). Five failed logins by *anyone* locked out *everyone* behind that edge for three hours, which is why the report looked intermittent (the shared bucket refills). `docker/frontend/nginx.conf` and `docker/frontend/nginx-proxy.conf` now enable nginx's realip module (`real_ip_header CF-Connecting-IP` + `set_real_ip_from` for Cloudflare's published edge ranges), so the `X-Real-IP` they already send carries the real visitor. Deliberately **no** backend change: `client_ip()` keeps trusting only the proxy-set `X-Real-IP` and the socket peer, never a client-supplied `CF-Connecting-IP` / `X-Forwarded-For`, so the AUT-303 spoof bypass stays closed — `set_real_ip_from` is the trust boundary, and a request arriving from outside a Cloudflare range is never rewritten. Adds `backend/tests/test_aut5460_cf_real_ip.py`, which pins every edge range in both configs, the `/api` proxy header that forwards the rewritten address, and the AUT-303 behaviour of `client_ip()`.

## [0.3.311] - 2026-10-04

### Changed (AUT-5532)
- fix(frontend): cleared the last 3 deprecated `withOpacity` call sites in `login_screen.dart` — the two background-gradient stops (`scheme.primary.withOpacity(0.75)`, `scheme.secondary.withOpacity(0.6)`) and the form-card `BoxShadow` (`Colors.black.withOpacity(0.18)`). PR #905 fixed only the logo-shadow `BoxShadow` and deliberately deferred these, leaving `dart analyze lib/screens/auth/login_screen.dart` at 3 `deprecated_member_use` infos; the file is now clean. Cosmetic only, no behaviour change: `withValues(alpha:)` keeps alpha as a double where `withOpacity` rounded to 8-bit, so `0.75` and `0.6` render identically and the card shadow shifts by 1/255 of alpha (`0.18` → `0.1804`). The remaining 45 occurrences across 17 files under `frontend/lib` (incl. `signup_screen.dart`) are out of scope.

## [0.3.310] - 2026-10-04

### Changed (AUT-5532)
- fix(frontend): the login screen's logo-circle drop shadow still used the deprecated `Colors.black.withOpacity(0.30)`, which emits a `deprecated_member_use` analyzer info (`'withOpacity' is deprecated … Use .withValues() to avoid precision loss`) on every `flutter analyze` run. Swapped to `Colors.black.withValues(alpha: 0.30)` — same rendered shadow (the two differ only in 8-bit rounding of the alpha channel), deprecation cleared. Cosmetic only, no behaviour change; raised during QA re-review of PR #787 (AUT-5524).
## [0.3.309] - 2026-10-04

### Fixed (AUT-5541)
- fix(valuation): comparables must match the vehicle's model year — a 2009 Toyota Crown was being valued off 2019 Crowns. Two causes: `market-data`'s `carsguide._filter_year` fell back to the **whole unfiltered listing set** whenever the requested year matched fewer than 3 results (which is exactly what a rare-year car hits), and the backend then aggregated that mixed set into the median. Year filtering now widens in tiers (0 → 1 → 3 → 5 years, first tier with 3 listings wins) and returns nothing past ±5, so a thin same-year sample surfaces as an honest "no market data" instead of a confidently wrong number. `market_data._build` applies the same filter server-side so a provider that ignores the requested year can no longer poison the median. `advisor.value.find_comparables` now year-checks each *listing* (a cache row for one model year can hold listings from another — the row-level filter was not enough) and sorts by nearest model year instead of newest-year-first, which is what put a 2019 Crown at the top of a 2009 car's comparison set. Adds `backend/tests/test_aut5541_comparables_year.py` and extends the `market-data` self-check.

### Fixed (AUT-5063)
- fix(security): depublish the compromised `demo@autobrainservice.app` / `demo`
  credential literal (CWE-798). `DEMO_PASSWORD` defaulted to `"demo"` in
  `backend/app/core/config.py`, so any `DEMO_MODE=true` run without an explicit
  `DEMO_PASSWORD` re-seeded the old demo password; the literal also shipped in
  `README.md`, `.env.example`, `docs/` and the Flutter login screen.
  `seed_demo()` / `reset_demo()` now fail closed — empty `DEMO_PASSWORD` skips
  and logs `demo_seed_skipped_no_password` / `demo_reset_skipped_no_password`
  instead of creating an account with a blank/default password, and
  `reset_demo()` skips before deleting so a reset can never wipe the demo
  environment for good. Adds the fail-closed cases to
  `backend/tests/test_seed_reset_demo.py`. No redeploy: AUT-2409 keeps deploys
  hosted-only and the demo stack is down (AUT-5057).
### Fixed (AUT-5529)
- fix(security): strip `DEMO_PASSWORD` before the fail-closed check in
  `seed_demo()` / `reset_demo()` (CWE-798 / CWE-521). A whitespace-only value
  (`DEMO_PASSWORD=" "`, e.g. a secret pasted with stray whitespace) is truthy,
  so the empty-string guard let it through and seeded a demo account whose
  password was a single space — guessable for anyone holding the public demo
  email. Both guards now strip first, and `seed_demo()` hashes the stripped
  value so a padded secret still matches what the operator types (as
  `seed_admin()` already did). Whitespace-only regression cases added to
  `backend/tests/test_seed_reset_demo.py`.

## [0.3.308] - 2026-10-04

### Fixed (AUT-5433)
- fix(backend): the hourly off-site backup task `app.workers.tasks.backup_offsite_hourly` crashed on **every** run with `TypeError: Logger._log() got an unexpected keyword argument 'reason'` — `app/services/backup_offsite.py` built a stdlib `logging.getLogger` but every call site passes structlog-style kwargs (`reason=`, `filename=`, `status=`, `error=`, `pushed=` …), so the first `logger.info` of the run raised before any push was attempted. Affecting EP2 Default (backend 0.3.305) and EP5 Hosted (0.3.307), i.e. off-site backups had not been pushing at all. The module now uses the project's `get_logger` structlog logger like every other service. The existing test could not catch it: pytest's logging plugin attaches a root handler, which makes `setup_logging()`'s `logging.basicConfig()` a no-op so the level stayed `WARNING` and `logger.info()` short-circuited before `_log()` ran — the suite now forces `INFO` and asserts the structlog-kwarg call path.

## [0.3.307] - 2026-10-03

### Fixed (AUT-5318)
- fix(backend): `_ensure_next_service` lost its function-local `list_completed_services` import in #888, so the AUT-5318 auto-suggest raised `NameError` and returned 500 on every odometer-triggered suggestion — i.e. adding a fuel or logbook entry to a vehicle with auto-suggest on and no scheduled service still created no service item. Restores the import.

## [0.3.306] - 2026-10-03

### Fixed (AUT-5318)
- fix(backend): auto-suggested service was never created for most vehicles. `_ensure_next_service` (AUT-1275) kept only completed services whose `service_type` was one of ten canonical types, returned early when the vehicle had no service history at all, and silently gave up when the AI gateway was unreachable — so adding a fuel or logbook entry created no scheduled service for a car with only "repair"/"tyres"/"custom" records, a car with no logged services, or during any AI outage. All completed services now count as history, history is no longer required, and a deterministic manufacturer interval (measured gap between past services, else 20,000 km / 12 months — the same baseline as the ai/ service-prediction fallback) creates the suggestion whenever the gateway does not answer. Adds `deterministic_next_due()` + `backend/tests/test_aut5318_deterministic_next_due.py` (no DB) and an end-to-end case in `backend/tests/test_odometer_priority.py` (gateway down, repair-only history, zero history).

## [0.3.305] - 2026-10-03

### Fixed (AUT-5268)
- fix(backend): migration `f7e8d9c0b1a2` called `PGInspector.get_constraints`, which does not exist in SQLAlchemy, so every `alembic upgrade head` raised `AttributeError` at that revision, fell back to `create_all` and left `alembic_version` stuck at two rows (EP2 Default). It now reflects the UNIQUE constraint via `get_unique_constraints` and no-ops when the constraint or the `passkey_credentials` table is absent (idempotent + offline-safe); adds `backend/tests/test_f7e8d9c0b1a2_passkey_unique.py` covering create / already-exists / downgrade / missing-table / offline paths.

## [0.3.304] - 2026-10-03

### Fixed (AUT-2203)
- fix(backend): `test_aut2203_station_annotations.py` constructed `FuelStats` with `avg_litres_per_fill` instead of the declared `avg_fill_litres` field, so 2 of its 7 tests raised a pydantic `ValidationError` and the `cost_per_km` / `avg_fill_cost` coverage the issue asked for never actually ran on `main`

## [0.3.303] - 2026-10-03

### Added
- Demo-tier frontend image build (`cannonfodder151/autobrain-frontend:demo`) in `dockerhub-publish.yml` (AUT-5261). The Demo stack had no frontend build job: `API_BASE_URL` is compiled into the Flutter bundle, so Demo needed its own image and the only pre-existing `:demo` artifact was built 2026-09-28 with Hosted's API base.

### Security (AUT-3977)
- backup: SSRF guard on `BACKUP_OFFSITE_URL` (`backend/app/core/config.py`). The
  backend now validates the configured off-site backup URL at startup and **fails
  closed**: only schemes `http`/`https`, only hosts that are loopback-free,
  link-local-free, and named in the new `BACKUP_OFFSITE_HOST_ALLOWLIST` exact-match
  list are accepted. Cloud-metadata literals (`169.254.169.254`), their
  decimal/hex/IPv4-mapped encodings, RFC1918 literals, and loopback aliases are
  rejected even when allowlisted. Anchoring on anything but the whole label set
  would let an attacker-registered domain such as `autobrain-backup.attacker.net`
  satisfy the rule, so the match is an exact, case- and trailing-dot-normalised
  host comparison.
- deploy(hosted): `docker-compose.hosted.yml` sets
  `BACKUP_OFFSITE_HOST_ALLOWLIST: ["backup"]` so the shipped default
  `BACKUP_OFFSITE_URL` stays authorised. Overriding the URL without adding the new
  host now makes the backend refuse to boot, by design.
- docs: `.env.example` documents `BACKUP_OFFSITE_HOST_ALLOWLIST` next to the other
  `BACKUP_OFFSITE_*` entries (the AUT-2390 compose diff gate requires every
  compose env key to be declared there).
- Guarded by `backend/tests/test_aut3977_backup_offsite_ssrff.py` (36 cases).

### Fixed (AUT-3978)
- fix(backup): `backup_offsite_hourly` wraps `run_backup_offsite()` in the
  persistent-loop `_run()` wrapper. Before the fix the async function was passed
  bare, so the coroutine was created and dropped — the task "succeeded" in
  ~0.001s and the hourly off-site push never fired. Guarded by
  `backend/tests/test_workers.py` and the real-task regression in
  `backend/tests/test_backup_offsite.py`.

## [0.3.302] - 2026-10-02
- fix(fuel): disable the SA (SAFPIS) feed (AUT-5072).
  `FUEL_SA_ENABLED: "true"` was set in both compose files
  (AUT-2610) with a seeded `fuel_sa_api_key` secret, but no
  `ingest_sa_*` function exists — `ingest_all_fuel()` only
  loops `wa`, `nsw`, `vic`, `qld`, so SA was nominally enabled
  and silently produced zero stations forever. The SAFPIS
  Direct API host `fppdirectapi.safuelpricinginformation.com.au`
  is NXDOMAIN (verified against the authoritative nameserver via
  public DoH) and the AUT-2372 research doc lists the production
  URL as "to be confirmed from registration" — no subscriber
  token was ever contracted. Building the ingester would have
  reproduced the AUT-4143 VIC dead-feed failure mode. Both
  `docker-compose.hosted.yml` and `docker-compose.prod.yml` now
  set `FUEL_SA_ENABLED: "false"` (same pattern as VIC/AUT-4976);
  the secret file stays mounted so re-enabling is a one-line flip
  once an aggregator is contracted. `/fuel/stations` and
  `/fuel/attribution` advertise only `wa`/`nsw`/`qld`, so SA
  coverage is not advertised. Guarded by
  `backend/tests/test_fuel_feed_flags.py`.

## [0.3.301] - 2026-10-02

### Fixed (AUT-5131)
- security(ci): corrected the `.trivyignore` reachability rationale for
  `CVE-2026-103111` (pcre2 OOB write). The old condition-2 paragraph
  claimed the nginx base image "ships no JIT-enabled pcre2 build for our
  config" — false: the pinned `nginxinc/nginx-unprivileged:stable-alpine`
  binary (nginx 1.30.5-r1, pcre2 10.48-r0) links `libpcre2-8.so.0` and
  imports `pcre2_jit_compile_8` (plus `pcre2_compile_8`,
  `pcre2_match_8`, `pcre2_pattern_info_8`) from its `.dynsym`, which is
  the proof that PCRE2 JIT is compiled in. The suppression itself is
  unchanged and stays approved: condition 1 (attacker-controlled regex)
  fails independently — nginx only matches the static
  `location ~ ^/(autobrain-assets|autobrainservice-assets)/` literal —
  and CPython 3.13 links no pcre2 at all. No entry added or dropped;
  the 2026-11-30 re-check date stands. Comment-only change, no runtime
  effect.

### Fixed (AUT-4718)
- security(ci,docker): repinned the two base images that were failing the
  `Security — base image CVE scan (trivy)` gate on `main`, and dropped the
  `.trivyignore` entries the bumps made redundant. The gate had been red on `main`
  since 2026-09-26, so every open PR looked like it had a regression.
  - `nginxinc/nginx-unprivileged:stable-alpine` → `@sha256:ed04ec1f…`
    (Alpine 3.24.2, `libexpat` 2.8.5-r0, `libuuid` 2.42.3-r1). Clears
    `CVE-2026-93990`, `CVE-2026-66046` and `CVE-2026-76641` (libexpat) plus all
    seven util-linux/libuuid and the `CVE-2026-80256` placeholder findings.
  - `python:3.13.15-slim-trixie` → `python:3.13.16-slim-trixie@sha256:6906dca8…`
    (Debian 13.7). Clears `CVE-2026-75804` / `CVE-2026-84782` (OpenSSL QUIC/DTLS),
    `CVE-2026-41992` (gzip), `CVE-2026-11822` / `CVE-2026-11824` (libsqlite3-0) and
    seven `perl-base` findings, and carries openssl `3.5.7-1~deb13u3` on both the
    amd64 and arm64 manifests.
  - All three nginx pins had drifted onto three *different* digests
    (`docker/frontend/Dockerfile` built `44275388…`, `trivy-image-scan.yml` scanned
    the amd64-only manifest `ee1643ae…`, and `libexpat-version-check.yml` watched
    `45ce1e2e…`). All three now pin the same multi-arch index, so the scan again
    covers the arm64 frontend we actually build.
- security(ci): added three time-boxed `.trivyignore` entries, each with its
  reachability argument, for CVEs whose fixes are published upstream but not yet in
  any published image: `CVE-2026-103111` (pcre2 OOB write — needs an
  attacker-controlled regex *and* JIT; CPython links no pcre2 and our nginx PCRE
  patterns are static), and `CVE-2026-97687` / `CVE-2026-97689` (urllib3 2.7.0 as
  pip's vendored copy — build-time only; the runtime HTTP stack is httpx).
  Re-check 2026-11-30.
- fix(ci): `trivy-image-scan.yml` passed `scanner: vuln` to
  `aquasecurity/trivy-action@v0.36.0`, which does not accept that input (it is
  `scanners`). GitHub logged `Unexpected input(s) 'scanner'` on all three scan
  steps and dropped the value.
- fix(ci): `libexpat-version-check.yml` compared a per-arch manifest digest
  (`regctl image digest --platform linux/amd64`) against `PINNED_DIGEST`, which holds
  the multi-arch index digest, so `unchanged` was never true and the daily job
  re-filed a duplicate Paperclip issue on every run. It now resolves the index
  digest, and its threshold is raised to 2.8.5-r0.
- Verified 2026-10-02 with trivy 0.70.0 against the edited `.trivyignore`: all three
  pinned base images return 0 findings at HIGH/CRITICAL with `--ignore-unfixed`
  (exit 0 each).

## [0.3.300] - 2026-10-02
- fix(ci): restore automatic deploys for the **Demo** and **Default** tiers.
  AUT-2409 narrowed `DEFAULT_TIERS` in `scripts/upgrade-instances.sh` to
  Hosted-only, so neither EP2 stack was ever redeployed again and demo
  (`demo.autobrainservice.app`) went 502 and stayed down. The full
  Demo → Default → Hosted promotion chain is back in the defaults, still
  health-gated per tier (AUT-107). Hosted keeps its 03:00–04:00 AEST window
  (AUT-2409 / AUT-5172); scope a `deploy-instances.yml` dispatch with the new
  `tiers` input to honour it.

## [0.3.299] - 2026-10-02
- fix(backend): `backup_offsite_hourly` now wraps `run_backup_offsite()` in the
  persistent-loop `_run()` wrapper. Before the fix the async function was passed
  bare, so the coroutine was never executed and the hourly off-site backup never
  ran.

## [0.3.298] - 2026-10-02
- fix(backup): the backend no longer runs a second retention engine against the
  off-site backup store. `backup_offsite.py::_apply_tiered_retention()` pruned
  by file **age** (via `_tier_for_age`) while `autobrain-backup` prunes by
  **count per tier directory** (`engine.py::_prune`, defaults hourly 24 /
  daily 30 / weekly 12) — two policies, one store. Age-derived tiers ignored
  the tier directory the API returns (a `daily/` snapshot 10 days old collapsed
  to one per ISO week) and the backend's `monthly` tier does not exist on the
  service side at all, so anything older than 24 weeks was deleted outright.
  Repro against `main` @ `0f1f9248`: a listing the service itself considers
  fully in-policy (24 hourly + 30 daily + 12 weekly) lost **29 of 66**
  snapshots. Removed `_apply_tiered_retention`, `_list_existing_offsite`,
  `_delete_offsite`, `_tier_for_age`, `_slot_key` and `_OFFSITE_TIERS`; the
  hourly push and the `BACKUP_OFFSITE_ENABLED` guard are unchanged. Per-tier
  retention is configured on the autobrain-backup instance
  (`retention.hourly` / `retention.daily` / `retention.weekly`). Regression test
  feeds the 66-snapshot in-policy listing through `run_backup_offsite()` and
  asserts one ingest POST and zero deletes. Note: this task was a no-op before
  AUT-3975 / PR #757, so no production data was lost yet.

## [0.3.297] - 2026-10-02
- fix(hosted): the hosted backend now runs `alembic upgrade head` before
  bootstrap, so migration-only changes (new index, constraint, column rename,
  data backfill) stop being dead code in production. Hosted booted straight
  into `app.db.bootstrap`, whose `create_all` fallback swallowed every
  migration failure — `alembic_version` sat at `aut4925_missing_tables` and
  `fuel_price_snapshots` existed only because `create_all` happened to build it.
  Guarded by `scripts/check-compose-consolidation.py` (with negative tests) and
  a new `alembic-migrations` CI job that proves a create_all-built database
  at the hosted stamp reaches head and that the pending revision performs real
  DDL instead of only bumping a version string.
- feat(alembic): add migration for `fuel_price_snapshots` — the table was only

### Fixed (AUT-4678)
- `scripts/check-compose-config.py` crashed with `KeyError: 'ai'` on `main`
  after the AUT-3153 merge removed the standalone `ai` service, so the hosted
  compose structural guard had been dead. Optional services are now filtered
  by presence (`SECRET_SERVICES` + `present()`), `BACKUP_OFFSITE_GUI_KEY_FILE`
  / `BACKUP_OFFSITE_INGEST_KEY_FILE` (and gh-runner's `github_pat`) are known
  secret files, and the corresponding plain-env keys are forbidden.
- `scripts/check-compose-consolidation.py` asserted the standalone `ai`
  service existed; it now asserts the merged gateway indirection
  (`AI_GATEWAY_API_KEY_FILE` / `AI_ROUTER_API_KEY_FILE`) lives on `backend`.
- `scripts/seed-secrets.sh` aborted immediately: a comment inside a `sed`
  backslash continuation (`# -e 's/^FUEL_VIC_API_KEY$/…' \`) terminated the
  pipeline, so `set -eu` killed the script and **no** secret file was ever
  seeded. Comment moved above the pipeline; `BACKUP_OFFSITE_GUI_KEY` /
  `BACKUP_OFFSITE_INGEST_KEY` are now mapped to secret files.
- New `.github/workflows/compose-checks.yml` runs every `scripts/check-*.py`
  plus `scripts/test_check_compose_config.py` on compose/script changes, so
  the guards can no longer rot unnoticed.

### Fixed (AUT-4327)
- test(frontend): add a regression test asserting the login logo renders inside a
  circular, black-background container and uses `BoxFit.contain`, so a
  non-square logo asset cannot silently stretch again. The layout fix itself
  already landed; this guards it.
- test(frontend): scope the login-logo regression test to the `ClipOval` subtree.
  `find.byType(Container).first` resolved to the gradient `Scaffold.body`
  Container, so the test failed for the wrong reason. Also add the test to
  `visual_regression.yml`, which previously never executed it.

## [0.3.296] - 2026-10-02

### Fixed (AUT-5032)
- test: three pre-existing failures in `backend/tests/test_workers.py` that
  reproduced on a clean `origin/main` checkout (not env-dependent, and not
  caused by the AUT-3827/AUT-3977 branch diff — root cause was the test
  harness, not the code under test):
  - `test_scheduled_backup_skips_on_missing_minio_credentials` asserted on
    `caplog` (stdlib `logging`), but the worker logs through `structlog`, so the
    records never reached `caplog`. It now uses
    `structlog.testing.capture_logs()` and asserts on the
    `reason="minio_credentials_missing"` event field, matching the pattern in
    `backend/tests/test_aut324_rego_log_redaction.py`.
  - `test_ingest_fuel_prices_no_typeerror_when_source_in_result` and
    `test_run_due_checks_runs_inner_coro_via_run` raised `NameError` at the
    `patch.object(...)` / `asyncio.new_event_loop()` call sites because
    `unittest.mock.patch` and `asyncio` were never imported. Both are now
    imported at module top.
  - No production code changed. `python3 -m pytest backend/tests/test_workers.py`
    is green (7 passed) with only `DATABASE_URL` + `SECRET_KEY` exported.

### Security (AUT-5041)
- deps: bump `pypdf` `6.16.1` -> `6.19.0` in `backend/requirements.txt` and
  `ai/requirements.txt`. 6.16.1 carried 8 known vulnerabilities
  (PYSEC-2026-4153..4160), which kept the `pip-audit-gate` job of
  `Publish images to Docker Hub` red on `main` and blocked every PR merge.
  `pip-audit --disable-pip --no-deps` over the deduplicated backend+ai pin
  list is now clean. The receipt worker's `_pdf_text()` and the reportlab PDF
  export paths are unchanged (`pypdf` is only ever a reader there); guarded by
  `backend/tests/test_deps_pypdf_pin.py` (floor raised to 6.19.0),
  `backend/tests/test_pdf_dos_regression.py` and the `test_api.py` PDF export
  tests.

## [0.3.295] - 2026-10-02
>>>>>>> theirs

### Added (AUT-594)
- demo/default compose digest pinning now tracked by update-compose-pins.py
- demo (EP2, stack 138) and default (EP2, stack 137) sync to Portainer via
  sync-compose-to-portainer.py in dockerhub-publish.yml merge-triggered workflow
- demo frontend registry drift resolved: switched from ghcr.io to Docker Hub
  cannonfodder151/autobrain-frontend:demo@sha256:db91b2b7...

### Fixed (AUT-594)
- demo/frontend registry drift (ghcr.io :hosted was never published, only
  Docker Hub :demo exists)
- update-compose-pins.py now supports Docker Hub (prefixless) registry and
  tier-specific frontend tags (:demo/:default)

### Fixed (AUT-514)
- fix(backend): add webauthn dependency + fix attestation enum for passkey tests; resolve test_auth_begin_unknown_user_returns_empty_allow failing due to missing webauthn module and incorrect AttestationConveyancePreference enum value (PR #1124)

## [0.3.320] - 2026-11-19

### Fixed (AUT-587)
- fix(frontend): add `formatDollarsPerLitre` helper to Servo Spy history screen so chart labels and tooltip share the cents-per-litre conversion; this helper was a mobile-only delta that `sync-mobile.sh` overwrote, breaking `sync-mobile.yml` (PR #1132)

## [0.3.319] - 2026-11-14

### Added (AUT-240)
- automated 2-day upgrade cycle: Docker rebuild + deploy demo→default→hosted, mobile rebuild + push to stores

### Fixed (AUT-296)
- stack_id param expansion in upgrade-instances.sh

### Fixed (AUT-2459)
- fix duplicated P<id> fallback in _parse_qld_direct_prices

<<<<<<< ours
=======
### Fixed (AUT-3080)
- fix(security): restrict CORS `allow_methods` to explicit set (GET/POST/PATCH/DELETE) and `allow_headers` to narrow list (Authorization, Content-Type, Accept, X-Requested-With). Add startup validator rejecting `CORS_ALLOWED_ORIGINS=["*"]` with `allow_credentials=True`.
# CI re-trigger
>>>>>>> theirs
