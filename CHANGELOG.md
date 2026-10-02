# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.


## [Unreleased]
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

### Fixed (AUT-3827)
- backup: include the `monthly` tier when listing off-site snapshots
  (`backend/app/services/backup_offsite.py`). Retention manages four tiers but the
  off-site listing flattened only `hourly`/`daily`/`weekly`, so monthly backups were
  invisible to `_apply_tiered_retention` — never deduped per month slot and never
  pruned past the 6-month window. Tier list is now a single `_OFFSITE_TIERS`
  constant. Guarded by `backend/tests/test_backup_offsite.py` (new).

### Fixed (AUT-4976)
- deploy(hosted): set `FUEL_VIC_ENABLED: "false"` in `docker-compose.hosted.yml`,
  matching `docker-compose.prod.yml`. The VIC Servo Saver endpoint
  `api.servosaver.com.au` is NXDOMAIN (AUT-4143), so the hosted nightly beat
  (`ingest-fuel-prices`) raised `FuelFeedError` for VIC on every run. NSW, QLD and
  SA feeds are unaffected. The VIC secret files stay mounted so the feed can be
  re-enabled when a paid VIC aggregator is available. Guarded by
  `backend/tests/test_fuel_feed_flags.py`.

## [0.3.294] - 2026-10-01

### Fixed (AUT-4911)
- deploy(hosted): remove the `gh-runner` service from `docker-compose.hosted.yml`.
  It carried an inline `build:` block, and Portainer cannot build service images for
  a remote endpoint with no uploaded build context, so every compose-pin sync of this
  file failed with `HTTP 500` on `PUT /stacks/122?endpointId=5` (body:
  `failed to deploy a stack: compose build operation failed: listing workers for Build`)
  — reproduced on EP5 and EP6. The ARM64 runner already runs as its own Portainer
  stack (`gh-runner-autobrain-arm64`, stack 123 on EP5) on the external
  `autobrain-hosted_default` network, and its image `autobrain-gh-runner:arm64-latest`
  is unpublished, so the inlined service could never have started on EP5 anyway.
- deploy(hosted): `scripts/sync-compose-to-portainer.py` now prints the Portainer
  response body on failure and exits 4 instead of logging a bare `HTTP Error 500`,
  so the next such error names itself in the CI log.
- ci: this entry lands as a `CHANGELOG.md`-only commit. The AUT-4911 merge itself
  shipped without one, so the post-merge `changelog-gate` job failed on `main` and
  took the `Publish images to Docker Hub` run down with it, leaving the release queue
  stuck. A changelog-only diff does not re-trip the gate.

## [0.3.293] - 2026-10-01

### Fixed (AUT-4919)
- fix(ci): stop lineage sync from committing editor backup files. `sync-mobile.yml`
  commits with `git add -A`, so a stray `CHANGELOG.md.bak` left in the
  `autobrain-mobile` working tree was swept into commit `b102347` and stayed
  tracked (140KB) in every clone. Two fixes: `autobrain-mobile` now gitignores
  `*.bak` and `*~`, and `scripts/sync-mobile.sh` runs a pre-flight that aborts
  the sync if a backup artifact is present on either side of the copy — before
  any file is written, so there is no partial sync. Covered by
  `scripts/test_sync_mobile_backup_guard.sh`.

### Fixed (AUT-4925)
- fix(backend): repair the Alembic head that hard-failed on every boot of the hosted
  stack. `alembic_version` read `aut3447_passkey_credentials`, but `passkey_credentials`,
  `engineers` and `engineer_reviews` did not exist, so head migration `f7e8d9c0b1a2`
  raised `UndefinedTableError: relation "passkey_credentials" does not exist`.
  `bootstrap()` then fell back to `create_all`, which could not repair the gap
  because `app/models/__init__.py` never imported those three models — so the
  version never advanced and the loop repeated indefinitely. Passkey sign-in and
  the engineer marketplace were both non-functional on hosted as a result. Three
  changes: `f7e8d9c0b1a2` is now guarded and no-ops when the table is absent; a new
  guarded migration `aut4925_missing_tables` creates the three tables
  column-for-column identical to the ORM models (including
  `engineer_reviews.updated_at`, which `a3661engineers` omits); and the three
  models are imported so the `create_all` fallback covers them. A new
  `test_every_model_table_is_exported_for_create_all` guard fails if any model
  class declaring `__tablename__` is not exported from `app.models`.

## [0.3.292] - 2026-10-01

### Security (AUT-4701)
- test(backend): add a PyJWT floor guard to `test_deps_transitive_cves.py` —
  `pyjwt >= 2.15.0`, so a future downgrade cannot silently re-expose
  GHSA-42vr-xj54-vc7v (unauthenticated `RecursionError` DoS via
  `PyJWKClient.get_signing_key_from_jwt` with `verify_signature=False`),
  which 2.14.0 does **not** fix. The pin guard itself is also hardened:
  `_pins()` now strips `[extras]` (`PyJWT[crypto]` -> `pyjwt`) and tolerates
  PEP 440 suffixes (`2.9.0.post0`), which previously raised `ValueError` and
  took down the whole module. The 2.15.1 pin itself already landed via
  AUT-4743 (#828).

## [0.3.291] - 2026-10-01

### Fixed (AUT-4855)
- ci(release): `scripts/bump-version.sh` printed `docker build` instructions that
  interpolated `"$CARTO_API_KEY"` even though the commands are only echoed, never
  run. Under `set -u` — how CI invokes it via `auto-bump.sh` — an unset
  `CARTO_API_KEY` killed the script at line 64 with `unbound variable`, after the
  CHANGELOG had been promoted but before the version bump could be committed. That
  broke the `auto-bump` job in both `Publish images to Docker Hub` and
  `Build hosted images (multi-arch)`, blocking every release off `main`. This was a
  regression introduced by AUT-4824 (PR #822). The three lines now print a literal
  `$CARTO_API_KEY` placeholder for the operator to substitute; the `set -u` guard
  is untouched. New `scripts/test-bump-version.sh` runs the real script in a
  sandbox with the key unset and set, asserting exit 0 and that the bump lands.

### Fixed (AUT-4824)
- docs(docker): the `CARTO_API_KEY` hard-fail introduced by AUT-4690 (PR #822)
  left three documented/scripted frontend build paths passing no
  `--build-arg CARTO_API_KEY`, so all of them failed if copied: the manual
  `docker build -f docker/frontend/Dockerfile` snippet in
  `docs/Deployment-and-Infrastructure/deployment-guide.md`, the three
  hosted/default/demo build commands printed by `scripts/bump-version.sh`, and
  the   stale "Empty -> key-less public basemap" comments in `.env.example`,
  `docker-compose.yml` and `docker-compose.prod.yml` (the empty default is
  intentional — it fails the build loud rather than shipping a watermapped map).
  No behaviour change. New `scripts/check-carto-build-arg-propagation.py`
  statically asserts that every documented/scripted frontend build passes the key;
  it now runs as the `carto build-arg propagation` CI job so the paths cannot
  silently regress. `scripts/publish-images.sh` also sources the key from `.env`
  and hard-fails early instead of letting `docker build` reject it, and
  `dockerhub-publish.yml` fails with a readable message when the
  `CARTO_API_KEY` secret is unset rather than surfacing an opaque error deep
  inside the build.

## [0.3.290] - 2026-09-30

### Fixed (AUT-2784)
- fix(ai): the AI gateway now imports its own modules relatively, so it is
  self-contained as `ai_app` in the shared backend image. `docker/backend/Dockerfile`
  copies `ai/app` to `ai_app` and runs it as a co-process on `:8001` inside the
  backend container, but every gateway module used an absolute `from app.…`
  import. In that image `app` resolves to the **backend** package, which has no
  `logging`, `modules`, `router_client` or `fallbacks`, so the gateway died at
  startup with `ModuleNotFoundError: No module named 'app.logging'` and every
  `/ai/` route 502'd. 48 import statements across 20 files converted; the
  standalone `ai/` suite is unchanged (109 passed, same 3 pre-existing failures).
- test(ai): `ai/tests/test_merged_image_layout.py` simulates the image layout
  (backend `app` + gateway `ai_app` side by side) and asserts the gateway both
  imports and serves `/health` + auth on `:8001`, plus an AST check that no
  absolute `app.*` import reappears. The standalone AI suite imports `app.main`
  and could never catch this class of breakage; the new file fails 3/4 on the
  pre-fix tree and passes 4/4 after.

## [0.3.289] - 2026-09-30

### Changed (AUT-3944)
- chore(deploy): the hosted `autobrain-backup` service is renamed to `backup`
  and is now the **single** backup container. `backup-agent` stays removed
  (AUT-3827 — its hourly snapshot push is the `offsite-backup-hourly` Celery
  beat task in `backend`), so the hosted stack runs one backup container
  instead of a GUI container plus a poller sidecar. GUI endpoint is unchanged
  (`127.0.0.1:8080` on the host, `/backups` bind mount preserved).
  `BACKUP_OFFSITE_URL` now defaults to `http://backup:8080`; **any EP5 stack
  env override of the old `http://autobrain-backup:8080` must be updated or
  hourly pushes stop on DNS failure.**

### Fixed (AUT-3944)
- fix(ci): `scripts/check-compose-consolidation.py` and
  `scripts/check-compose-config.py` no longer crash or pass vacuously on the
  consolidated stack — both still asserted the `ai` service that AUT-3824
  removed (`KeyError: 'ai'`), and neither allowed-listed the
  `backup_offsite_*` secret files added by AUT-3827. Both now assert the exact
  10-service set and the `backup` DNS name.

## [0.3.288] - 2026-09-30

### Security (AUT-4743)
- fix(backend): bump `PyJWT[crypto]` 2.13.0 -> 2.15.1. 2.13.0 carries 12 known
  CVEs (CVE-2026-101917/101918/102265-102274), which made both `pip-audit-gate`
  and the resolved-tree scan (AUT-1189) fail on every PR and on `main` — it was
  blocking the hosted deploy pipeline, not just this PR. The API used by
  `app/core/security.py` and `app/services/iap.py` (`encode`/`decode`/
  `get_unverified_header`/`PyJWTError`/`InvalidTokenError`) is unchanged.
### Fixed (AUT-4690)
- **CI:** `docker/frontend/Dockerfile` now hard-fails when `CARTO_API_KEY` is
  unset/expired, and asserts the key value is actually present in the built
  `main.dart.js`. Previously an empty secret produced a *green* build and the
  Servo Spy map silently fell back to the watermapped public basemap, only
  caught weeks later by a human QA curl (AUT-4533, AUT-4649). The empty-key
  check runs before `flutter build web` so it fails fast.

## [0.3.287] - 2026-09-30

- **CI (AUT-1029):** `dockerhub-publish.yml` gains a `dedupe-main-queue` job that cancels superseded `queued`/`pending` publish runs on `main` before the heavy jobs start, so a burst of merges no longer queues N full 5-image builds behind the 3-runner fleet. In-flight runs are never cancelled (AUT-967/AUT-1756 behaviour preserved).

### Changed (AUT-4503)
- chore(deploy): the EP2 9Router (`10.0.3.17:20128`) is a managed Portainer
  stack (`9router`, id 128) from `docker-compose.9router.yml` instead of a loose
  `docker run` container — it was invisible to Portainer's stack view, so it had
  no consistent update path and no health signal
- chore(deploy): the EP2 router image is pinned by digest
  (`decolua/9router:0.5.91@sha256:efc6e88c…`) — the same image the floating
  `:latest` tag was already resolving to, so no version change
- feat(deploy): the EP2 router stack carries an `/api/health` healthcheck; the
  loose container had none
- docs(deploy): document all three 9Router instances (EP2 stack, EP5 inside
  `autobrain-hosted`, EP6 has none and uses the EP2 one) and the two ways to
  break the shared `:20128` route

## [0.3.286] - 2026-09-29

### Added (AUT-3503)
- feat(backend): WebAuthn passkey sign-in is functional end-to-end (the route
  skeleton shipped in AUT-3447 but could never complete a ceremony)
- fix(backend): passkey registration verification now parses the real
  `AuthenticatorAttestationResponse`; it previously passed `response=None`, so
  every registration attempt failed
- fix(backend): `/auth/passkey/authenticate/complete` now returns
  `access_token` + `refresh_token`; it minted both tokens and then discarded
  them, so a successful passkey assertion could not sign the user in
- fix(backend): expected origin and RP ID are derived from `APP_BASE_URL`
  instead of the client-supplied `Origin` header, which made the origin check a
  no-op (an attacker could echo any origin)
- fix(backend): WebAuthn challenges live in Redis with a 5-minute TTL so they
  survive across workers and restart; the in-process dict was shared by
  nothing when the API scaled past one worker
- feat(backend): alembic `f7e8d9c0b1a2` adds a unique constraint on
  `passkey_credentials (user_id, credential_id)` so one authenticator cannot
  be registered twice for an account

### Fixed (AUT-3661)
- fix(backend): `EngineerSortBy` no longer inherits from `list`, which raised
  `TypeError: multiple bases have instance lay-out conflict` on Python 3.13
  and broke app import
- fix(backend): `/api/v1/engineers` imported `EngineerSearchResult` and
  `EngineerSearchResponse` from the service module, which does not export
  them; both now import from `app.schemas.engineer` (also fixes
  `EngineerResponse` being undefined)

## [0.3.285] - 2026-09-28

### Fixed (AUT-4143)
- fix(backend): disable VIC Servo Saver fuel feed — endpoint `api.servosaver.com.au` returns NXDOMAIN and would raise `FuelFeedError` instead of returning 0 stations; set `FUEL_VIC_ENABLED="false"` in `docker-compose.prod.yml` and commented out unused secret seeds in `scripts/seed-secrets.sh` until a paid VIC aggregator is available

## [0.3.284] - 2026-09-28

### Fixed (AUT-4317)
- fix(frontend): match both MinIO bucket prefixes (`autobrain-assets` on
  dev/hosted, `autobrainservice-assets` on demo/default) in nginx so
  community-hub photos load instead of serving the SPA shell; the regex
  location forwards the original URI (with its bucket prefix) to MinIO

## [0.3.283] - 2026-09-28

### Fixed (AUT-4327, AUT-4357)
- fix(frontend): login, signup and server-setup logo is no longer stretched (`BoxFit.cover` → `BoxFit.contain`) and sits in a black circle instead of a white one, on all three auth screens (AUD-427 user report)
- fix(frontend): `ApiClient.getCachedDecoded` no longer throws when the local cache backend is unavailable (web/sqflite); the vehicle manage screen, timeline, and every other cache-first screen fall through to the network path instead of failing to load

## [0.3.282] - 2026-09-27

### Changed (AUT-4289)
- fix(frontend): remove the "Petrol Prices" feature tile from the home screen feature grid; `PetrolPriceMapScreen` itself is unchanged and still reachable from `frontend/lib/screens/fuel/petrol_price_map_screen.dart`

## [0.3.281] - 2026-09-27

### Fixed (AUT-4259)
- fix(backend): merge alembic heads `a3661engineers` (engineer marketplace) and `aut3447_passkey_credentials` (WebAuthn) via new merge revision `m3rge07`; restores single-head guarantee so `alembic upgrade head` works and pytest-smoke gate passes

### Fixed (AUT-3228)
- fix(tests): prevent `pumpAndSettle` timeout in desktop layout golden tests by adding `ConnectivityService.testMode` flag and `setOnline()` setter; tests now disable the connectivity-plus stream listener and force online state, allowing all 6 golden tests (1280/1440/1920 × HomeScreen + VehicleListScreen) to settle.

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
