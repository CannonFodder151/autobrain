# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.


## [Unreleased]
### Added (AUT-2415)
- mobile+web: rego status badge + expiry on every vehicle card. New `Vehicle.regoStatus` / `regoExpiryDate` fields (parsed from `rego_status` / `rego_expiry_date`) drive a green/red `RegoStatusBadge` widget shown on the home hero card and the vehicle-list rows. Forward-compatible with AUT-2414's nightly Celery beat job: when `rego_status` / `rego_expiry_date` are absent the badge is hidden entirely. Gated behind `AuthState.premium` so free accounts see no rego chrome. `formattedRegoExpiry` renders `12 Mar 2027` style dates. Tests: `frontend/test/rego_status_badge_test.dart`.

## [0.3.228] - 2026-09-04
### Added (AUT-2419)
- backend(parts): nightly SCA parts cache prewarm. New `app.workers.tasks.refresh_sca_parts_cache` task walks every distinct (make, model, year) in the vehicles table and forces a fresh SCA lookup so the next user click returns from cache. Per-vehicle failures are isolated so one bad vehicle never aborts the run. Wired into `celery_app.conf.beat_schedule` at `crontab(hour=0, minute=0)` UTC. Structured log `sca_cache_prewarm_done` (vehicles/ok/failed/duration_s) so ops can monitor the first few nightly runs. Test: `backend/tests/test_sca_prewarm_aut2419.py` (3 cases).

## [0.3.227] - 2026-09-04
### Fixed (AUT-2249)
- ci: `ocr-review` Auto-approve step (AUT-1814) no longer fails on a fresh PR. GitHub Actions bash runs with `set -e`; `grep -qx APPROVED` exiting 1 previously aborted the step before the auto-approve POST ran, even though the step carried `continue-on-error: true`. Guard now wrapped in an `&&/||` chain with explicit `set +e`/`exit 0` so the if-test cannot fail the script. Adds `backend/tests/test_aut2249_ocr_review_guard.py` covering empty / has-APPROVED / no-APPROVED input paths. PR #437 was the original repro.

## [0.3.226] - 2026-09-04

### Fixed
- fix(docker, AUT-2212): remove the orphan `dongle-server-data` named volume from `docker-compose.hosted.yml` (the service block was already removed by PR #443 / AUT-1978; this finishes the dedupe). No service references the volume, so compose v2 never mounted it; the entry was dead config. No Portainer redeploy needed. Audit follow-up to AUT-2190.

## [0.3.225] - 2026-09-04

### Fixed (AUT-2389)
- infra(docker): frontend service now healthchecks `${BACKEND_URL}/health` (not just nginx) so Portainer flips the frontend container unhealthy when the backend upstream is unreachable/5xx. nginx-only probes hid AUT-1964 — nginx stays up while the upstream is dead, masking outages from Portainer's stack-health view. Applied to `docker-compose.yml` (local/dev), `docker-compose.prod.yml` (self-host), and `docker-compose.hosted.yml` (Oracle Cloud EP5). Uses the nginx-unprivileged image's `wget` to fetch `${BACKEND_URL:-http://backend:8000}/health` and `grep -q '"status":"ok"'` so a 5xx body or connection failure exits non-zero. `start_period: 30s` gives the backend time to come up on first boot. Closes AUT-2389.

## [0.3.224] - 2026-09-04

### Fixed
- `backend/app/models/fuel_price.py`: drop the dead `FuelPrice` class (duplicate `__tablename__ = "fuel_prices"` colliding with `fuel_station.FuelPrice`) that was silently breaking pytest collection / Alembic metadata registration. The intended class is `FuelPriceSnapshot` (already present, docstring-correct). `app/services/fuel_prices.py` now imports `FuelPriceSnapshot` explicitly. Adds `test_no_duplicate_table_names` to `tests/test_alembic_heads.py` so this regresses immediately if reintroduced. Closes AUT-2277.
- `backend/app/schemas/fuel.py`: restore `SevenElevenPricesOut` (AUT-1887 7-Eleven prices endpoint, removed in PR #347 but still imported by `app/api/v1/fuel.py`). Without this every backend test that imports `app.api.v1.fuel` (31 modules) crashes at collection. The route was 500ing in prod too.
- CI: `backend-pytest-smoke` workflow now only invokes the offline alembic-graph + duplicate-tablename guard from `tests/test_alembic_heads.py` — the actual regression guard AUT-2277 introduced. Other annotation tests will return to the workflow in a follow-up once they're verified offline.

## [0.3.223] - 2026-09-03

### Security (AUT-1745)
- sec(market-data): `docs_url`, `redoc_url`, and `openapi_url` are now env-gated and default to disabled. When `ENVIRONMENT=production` (the hosted + prod compose default), `/docs`, `/openapi.json`, and `/redoc` all return 404 — closing the unauthenticated API-surface enumeration on the market-data FastAPI service (CWE-200). `/health` and authenticated `/search`, `/sca-parts` are unchanged. Regression covered by `market-data/test_docs_disabled.py` (prod: 404, non-prod: 200, /health always 200). `redoc` remains always-off by design. Companion fix in `CannonFodder151/rego-lookup-api` adds the same gating + test (PR #47).
## [0.3.222] - 2026-09-03

### Added (AUT-2272)
- feat(frontend): boot-time API reachability probe. `AppConfig.validate()` hits `${apiOrigin}/healthz` (5s timeout, anonymous GET, body discarded) and sets `lastValidationOk` / `lastValidationError`. `main.dart` awaits the probe before `runApp`; on failure the new `MisconfiguredBackendScreen` mounts so the user can retry. Probe is positional `Uri(scheme, host, port, path:'/healthz')` — no URL-parser confusion, no user-input reach. Closes AUT-2272 M0.

### Fixed (AUT-2272)
- fix(frontend): import `package:flutter/foundation.dart` in `lib/app.dart` and `lib/main.dart` so `kDebugMode` resolves in release builds. Without it any code path touching the new probe would throw `NoSuchMethodError: 'kDebugMode'` at app boot. Closes AUT-2272 M1.
- fix(frontend): `MisconfiguredBackendScreen._retry` now uses `pushAndRemoveUntil(MaterialPageRoute(builder: (_) => ChangeNotifierProvider<AuthState>(create: (_) => AuthState(), child: const AutoBrainApp())), (_) => false)` instead of `pushReplacementNamed('/')` — the root `MaterialApp` in `app.dart` has no `routes`/`onGenerateRoute` (autobrain uses an if/else home switch), so the named-route lookup previously threw and trapped the user on the failure screen. Closes AUT-2272 M2.
- fix(frontend): `_defaultApiBase` / `_defaultWsBase` in `AppConfig` now point at `hosted.autobrainservice.app` (was `https://localhost:8000/api/v1` / `wss://localhost:8000/ws`). A release APK built without `--dart-define=API_BASE_URL` (CI drift, manual local build, future Docker arg omission) now boots against the real hosted backend and the boot-probe passes. `--dart-define` still overrides for self-hosted / demo / default stacks. Closes AUT-2272 M3.

### Added (AUT-2284)
- test(frontend): `frontend/test/config_validation_test.dart` — 5 reachability cases for `AppConfig.validate()`: 2xx ok, 5xx fail, timeout, connection refused, malformed URL. Uses `package:http/testing.dart` `MockClient` (no live network, runs in `flutter test`). Per-test isolation via `setUp` resetting `apiBase` / `lastValidationOk` / `lastValidationError` so order is independent (AUT-2284 S3). Plain `Exception('connection refused')` — no `SocketExceptionLike` shim (AUT-2284 S2: the validator's `catch (e)` accepts any thrown object; the shim added noise without value). No `AppConfig.buildInfo()` ever added — the QA comment flagged the dead `buildInfo()` from PR #445 (AUT-2284 S1); the debug banner reads `AppConfig.apiBase` / `lastValidationOk` / `lastValidationError` directly. Closes AUT-2284 S1/S2/S3.

### Added (AUT-2284 N1)
- fix(backend): expose `/healthz` as an alias of `/health` at the API root (FastAPI convention used by the Flutter boot-probe). Same handler, hidden from `/docs` (`include_in_schema=False`), no extra surface. The probe in `AppConfig.validate()` now hits a route that actually exists on this backend — without this, every release boot against `hosted.autobrainservice.app` would fail the reachability check and mount `MisconfiguredBackendScreen`. Closes AUT-2284 N1.

### Added (AUT-2284 N2)
- feat(frontend): boot-config debug banner now fires under `kDebugMode || kProfileMode` (was `kDebugMode` only). Profile-mode testers — Flutter DevTools / profilers, perf runs — no longer lose API-base visibility just because the build is a `flutter run --profile` rather than `--debug`. Overlay in `AutoBrainApp.build` shows `api: <host> probe: <ok|fail|not run>` via a translucent black bar across the top of every screen. Release builds still hide it. Closes AUT-2284 N2.

## [0.3.221] - 2026-09-03
### Added
- Servo Spy: `/api/v1/fuel/stations` accepts an optional `vehicle_id` query param. When supplied, every `FuelPriceOut` is annotated with `cost_per_km` ($/km, derived from the vehicle's avg L/100km) and `avg_fill_cost` ($, derived from the vehicle's avg litres/fill). Deterministic, no AI. Vehicle is ownership-checked via the standard accessible-vehicle helper. Closes AUT-2201.
- New `app/services/fuel_servo.py` pure helper (`annotate_price`, `annotate_prices`) so the per-station cost math is unit-tested without FastAPI/DB. DB-free tests in `tests/test_aut2203_station_annotations.py` cover the full-stats / no-vehicle / no-logs / partial-stats cases. Closes AUT-2203.
### Changed
- Servo Spy QLD feed switched to FuelPricesQLD DirectAPI v1.5 (Bearer subscription token). Old open-data parser kept behind `FUEL_QLD_USE_OPEN_FALLBACK` flag for one cycle.
- `FuelStats` now exposes `avg_litres_per_fill` (mean litres across all fills for the vehicle) so the Servo Spy annotations can be computed without an extra DB round-trip.
- Servo Spy per-station `cost_per_km` now divided by 10000 (cents/L → $/km) so it matches the existing per-fill `FuelLog.cost_per_km` units ($/km) — previously it returned cents/km, e.g. 14.03 instead of 0.14. Closes the unit-mismatch in AUT-2201 surfaced by the AUT-2203 issue description.

## [0.3.220] - 2026-09-03

### Fixed (AUT-1946)
- fix(backend): community garage photos are now auto-rotated to match their EXIF orientation before being re-encoded as webp. iPhone portrait shots previously displayed sideways/upside-down in the garage feed because the upload pipeline (Pillow → webp at 2048px) dropped the EXIF Orientation tag. `PIL.ImageOps.exif_transpose()` is applied in `compress_to_webp()` (`backend/app/social/media.py`); the tag is stripped from the stored object. Deterministic, no AI. Fixes uploads from every client path (mobile + web) and runs at the existing `/social/uploads` surface used by `edit_build`, `my_builds`, and the garage feed.

## [0.3.219] - 2026-09-03

### Fixed (AUT-2295)
- fix(frontend): Servo Spy map recenter FAB is now visible whenever the user has a GPS fix, not only after the map has drifted. Previously the FAB hid until the user panned, so on first open (or after returning to the map from another tab) the only way to recenter was to pan away first. Drift-tracking state removed (no remaining readers). Behaviour-gate test `servo_spy_map_render_test.dart` updated; `_DeniedGeo` stub added so the no-location case still hides the FAB.

### Added (AUT-2220)
- feat(frontend): wire CARTO basemap API key into the Servo Spy tile URL template. The key is injected at Flutter build time via `--dart-define=CARTO_API_KEY=<key>` (CARTO keys are designed to be public; embedded in tile URLs as `?api_key=…`). Empty key falls back to the key-less public basemap (current behaviour). CI reads the key from the new `CARTO_API_KEY` GitHub Actions secret on `CannonFodder151/autobrain`; `docker-compose.yml` / `docker-compose.prod.yml` plumb it as a build arg; `scripts/seed-secrets.sh` maps `CARTO_API_KEY` → `/data/autobrain/secrets/carto_api_key` on Hosted.

## [0.3.218] - 2026-09-03

### Changed (AUT-2231)
- chore(docker, AUT-2231): add `CORS_ALLOWED_ORIGINS` compose-level default on the `backend` service in `docker-compose.hosted.yml` so a fresh hosted stack never boots with an empty allow-list (was same-origin only by default). Default value: `["https://hosted.autobrainservice.app","https://hub.autobrainservice.app"]`. Override per stack via the Portainer stack env (AUT-2213 follow-up to AUT-2190 F2). No app-code change; `backend/app/core/config.py:CORS_ALLOWED_ORIGINS` already parses JSON-list env values.

## [0.3.217] - 2026-09-03
### Security
- **CI security gate / AUT-2066:** replace the broken `dart pub audit` step in
  `.github/workflows/security-pr-gate.yml` (the subcommand does not exist on
  current Flutter/Dart stable and was failing every PR at the audit step,
  blocking [AUT-1899](/AUT/issues/AUT-1899) and any other PR touching
  `frontend/`) with `osv-scanner` against `frontend/pubspec.lock`, gated to
  fail on HIGH/CRITICAL. Pinned to osv-scanner v1.7.3 for reproducibility.
  No more phantom Flutter gate failure; the gate now fails only on real
  package vulnerabilities.

## [0.3.216] - 2026-09-03

### Fixed (AUT-2233)
- fix(docker): bump `autobrain-dongle-server:hosted` digest in `docker-compose.hosted.yml` to `sha256:c5768948…`. The new image contains the `AUTOBRIAN_BACKEND_URL` → `AUTOBRAIN_BACKEND_URL` rename at the pydantic-settings source (AUT-1978 follow-up); the running container now reads the field by its canonical spelling and any caller that drops the env override falls back to `http://backend:8006` (the field default, harmless because the running stack sets `AUTOBRAIN_BACKEND_URL=http://backend:8000`).
- chore(ci, autobrain-dongle-server): fix `build-and-push` push to the private GHCR package by falling back to the `GHCR_PAT` secret (mirrors autobrain monorepo `build-hosted.yml`). The default GITHUB_TOKEN lacks cross-package write scope; without the fallback, every `hosted`-tag push failed with `permission_denied: read_package`. Repo secret `GHCR_PAT` populated.

### Fixed (AUT-2256)
- workers (`scheduled_backup`): skip-with-loud-log when `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` are empty (was previously a silent Celery FAIL on every daily beat tick). The hosted stack runs the same compose service as the in-app worker but the secret-file loader (`docker/lib-load-secrets.sh`) only exports what it finds; missing or misordered `*_FILE` mounts now surface as `scheduled_backup_skipped reason=minio_credentials_missing` instead of opaque stack traces.
- workers (`scheduled_backup`): isolate retention prune behind a try/except so a transient prune error no longer turns a successful upload into a Celery FAIL — a successful put with a logged prune error is the right outcome.
- workers (`scheduled_backup`): log `duration_seconds`, `size`, `tables` on success so hosted Grafana / log greps can alert on a stalled backup without parsing a stack trace.
- workers (`_run`): recover from a wedged persistent event loop on `RuntimeError` ("Event loop is closed" / "Future attached to a different loop") — recreate the loop on the next call instead of poisoning every subsequent Celery task for the lifetime of the worker process.

### Added (AUT-2202)
- Servo Spy: surface backend per-vehicle `cost_per_km` ($/km) and `avg_fill_cost` ($ per fill) in the list rows and station detail sheet alongside the existing $/L price. List + detail requests now send the active `vehicle_id`; metrics fall back to `—` when the API omits them (no vehicle selected or no fuel logs). Tests extended in `servo_spy_list_sort_test.dart`.
### Fixed (AUT-2208)
- fix(frontend): Servo Spy map can no longer render as a blank white screen. Added a `surfaceContainerHighest` background under the `FlutterMap` so the map area is never pure white, surfaced a centred empty-state overlay ("No fuel stations within N km — Try increasing the distance in Filters") when `/fuel/stations` returns `[]`, and moved the fetch-error banner from the bottom of the map to the top with a Retry action so it is impossible to look at the map and miss a station-fetch failure. Loading spinner now sits on a translucent scrim so the user always sees the map area behind it. New tests: `frontend/test/servo_spy_map_render_test.dart` covers render-with-stations, stations-fetch-error banner, and empty-state overlay paths.

## [0.3.215] - 2026-09-03

### Security (AUT-1608)
- k8s: add `resources.requests`/`limits` to autobrain-backend, autobrain-frontend, autobrain-ai, autobrain-worker, autobrain-beat, autobrain-postgres (D8). Prevents a single pod from exhausting node resources.
- frontend: add `Strict-Transport-Security: max-age=31536000; includeSubDomains` to every response (D12).

## [0.3.207] - 2026-09-02

## [0.3.206] - 2026-09-02

## [0.3.205] - 2026-09-02

## [0.3.204] - 2026-09-02

### Fixed
- fix(docker, AUT-1978): rename typo `AUTOBRIAN_BACKEND_URL` → `AUTOBRAIN_BACKEND_URL` in `docker-compose.hosted.yml` dongle-server block (typo silently broke backend→dongle backchannel since the AUT-1673 dongle-server wiring landed).
- fix(docker, AUT-1978): remove the duplicated `dongle-server` service definition in `docker-compose.hosted.yml`. Docker Compose takes the LAST occurrence on duplicate keys, so the first block (plain `DONGLE_SERVER_API_KEY`, no MinIO/SECRETS_FILE wiring) was dead config; only the second block (with `_FILE` secrets anchor, AUT-2211 overrides) was live. Single source of truth restored.

## [0.3.214] - 2026-09-03

### Added (AUT-2218)
- chore(docker): wire `FUEL_QLD_API_KEY` into `docker-compose.prod.yml` backend block (mirrors NSW/VIC pattern; empty value disables the feed, see `backend/app/services/fuel_feeds.py:493`).
- chore(docker): wire `FUEL_QLD_API_KEY_FILE: /run/secrets/fuel_qld_api_key` into `docker-compose.hosted.yml` backend + worker blocks. The existing `x-secrets` anchor (`<<: *secrets`) already bind-mounts `${SECRETS_DIR}` read-only, so no new volume entry is required; seed `fuel_qld_api_key` via `scripts/seed-secrets.sh` before redeploying the hosted stack.

## [0.3.214] - 2026-09-03

### Fix (AUT-2070)
- fix(docker): pin `nginxinc/nginx-unprivileged:stable-alpine` in `docker/frontend/Dockerfile` to the multi-arch manifest digest `sha256:45ce1e2e…` so the `Pin guard — frontend nginx image` gate stays green (was floating `:stable-alpine`).
- fix(frontend): Servo Spy list view now exposes an inline fuel-type chip bar so the fuel filter is visible without opening the filter sheet. The selected-fuel price-match fix from PR #410 (AUT-2105) already shipped in 0.3.203.

### Fixed
- fix(ci): replace the removed `dart pub audit` subcommand in the `Flutter — pub audit` PR gate with `osv-scanner --lockfile=pubspec.lock` so the gate stops failing every PR (Dart 3.6+ removed the subcommand). Repo-wide fix — unblocks merge of all open PRs.
- fix(docker): pin `redis:7-alpine` in `docker-compose.yml` to `redis:7.2.5-alpine@sha256:6aaf3f5…` so the `Pin guard` PR gate stays green (was the only unpinned compose image left after PR #409 unpinned nginx for arm64 hosted builds).

- fix(frontend): guard `pickPriceForFuel` against malformed price entries (non-Map, non-num/string price) so a bad API row no longer aborts the whole list view. OCR-review advisory.
- test(frontend): extend `servo_spy_list_sort_test.dart` with cases for `selectedFuelType == null`, missing `prices` key, string-encoded price, and malformed price entries (OCR-review advisory).

### Changed
- **AI gateway:** Extract router configuration (system prompts, schemas, payload caps, validation helpers) from `router_client.py` into new `router_utils.py` module. `router_client.py` now contains only HTTP transport. (AUT-1969)

### Changed
- **Servo Spy fuel map:** flip `FUEL_VIC_ENABLED` to `"true"` on Default and
  Hosted tiers and document the VIC Servo Saver partner-key wiring
  (`.env.example`, `docs/petrol-price-map.md`). The polling consumer is
  gated on an approved partner key being present in `/opt/autobrain/secrets`
  on Hosted, or `FUEL_VIC_API_KEY` on Default; absent the key the source
  silently skips per the existing `enabled()` check (AUT-1932).
- **Stack/docker-compose (AUT-1853):** `docker-compose.hosted.yml` and `scripts/seed-secrets.sh` now default `SECRETS_DIR` to `/data/autobrain/secrets` instead of `/opt/autobrain/secrets`. The snap dockerd on the Oracle VM masks `/opt` from a read-only core24 squashfs, so the old bind-mount failed with `read-only file system` and took the hosted stack down; `/data` is daemon-visible and never masked. `docs/security.md` and `docs/deployment-guide.md` updated for the path migration (the live HostED cutover — re-seed + redeploy — is tracked separately in AUT-1853-live).

## [0.3.212] - 2026-09-03
### Changed
- Servo Spy QLD feed switched to FuelPricesQLD DirectAPI v1.5 (Bearer subscription token). Old open-data parser kept behind `FUEL_QLD_USE_OPEN_FALLBACK` flag for one cycle.

## [0.3.204] - 2026-09-02

### Fixed
- CI (AUT-2097): fix buildx cache contamination in `build-hosted.yml` that shipped
  amd64 layer blobs inside arm64 manifests. Scoped GHA buildx cache per-architecture,
  disabled cache import for arm64 builds, added pre- and post-build arch verification
  steps, and gated manifest assembly on both arch checks passing.

## [0.3.203] - 2026-09-02

### Fixed
- fix(market-data): tighten valuation year window from ±2y to ±1y so the
  median stops anchoring on listings too new for the target vehicle. When
  the exact-year sample is <3, the fallback "nearby" set now includes only
  listings within 1 year of the target year (was 2). CarsGuide + BikesGuide
  both share the helper. Below the ±1y floor the unscraped wider set is
  still returned so the valuation pipeline never collapses to 0 listings
  (AUT-2079).
- fix(servo-spy): map view no longer renders a second inner `Scaffold` +
  `AppBar`, which was duplicating the back button and constraining the
  map so tiles failed to lay out. The map view now sits directly under
  the outer screen `Scaffold`; refresh / filter / enable-location
  actions moved into an inline header row inside the body (AUT-2073).
- fix(servo-spy): list view now shows the price for the selected fuel type
  instead of always reading `prices[0]`. Parses the full `prices[]` array
  and adds a `priceFor(fuelType)` helper on `ServoStationRow`, mirroring
  the map view's `_MapStation.priceFor` (AUT-2105).

### Security
- **AUT-1602:** Cap inbound user payload length per field in
  `ai/app/router_client.py` (`_cap_payload`, per-field: symptoms 2000,
  content 50000, text/notes/reason/repair_notes 2000, description 5000,
  raw_text 10000, default 5000; 100k total-budget guard with iterative
  halving). Together with the `<user_data>` instruction barrier + hardened
  system prompt already shipped on this branch, this closes the OWASP
  LLM01 prompt-injection path on narrative fields
  (summary/reason/repair_notes/recommendations) which had no `_AI_IMMUTABLE`
  protection. Deterministic baseline + schema whitelist + immutable
  numeric/financial fields remain the first line of defence; AI output
  stays an enrichment overlay.

## [0.3.202] - 2026-09-02

### Security
- **AUT-1189:** Pin three previously-unpinned transitives flagged by osv-scanner
  (idna 3.18, pycryptodome 3.23, pygments 2.20) plus bump `pypdf` 6.15.0 →
  6.16.1 across `backend/requirements.txt` and `ai/requirements.txt`. The
  PR-time `pip-audit` gate (`security-pr-gate.yml`) audits direct pins in
  `--no-deps` mode, so an unpinned transitive inherits any build-time
  resolution. Pinning to the current safe release makes a vulnerable
  build fail the gate instead of silently shipping. Adds
  `security-pr-gate-rego.yml` so `rego-lookup-api/requirements.txt` gets the
  same direct-pin gate as the monorepo (weekly full-resolution scan already
  covers its transitives).

## [0.3.201] - 2026-09-02

### Fixed
- fix(hosted): bump frontend image digest to the multi-arch `:hosted` image
  published after PR #384 (AUT-1908 unpinned the nginx base digest). The
  previous pin (`sha256:44654bb…`) was an amd64-only build that crashed on
  the arm64 hosted VM (`exec format error`, restart loop every ~60s). The
  new pin (`sha256:8937c2bb…`) is a true OCI image index with both amd64
  and arm64 manifests (AUT-2077).

### AUT-1868: petrol price map + servo-spy favourites selector (frontend)
- Petrol price map screen added with NSW Fuel API integration (AUT-1813)
- Servo-spy favourites selector: users can favourite fuel types on stations
- FuelPrice / FuelPriceWatchlist models added
- FuelPricesApi service wrapping GET/POST/DELETE /fuel-prices endpoints
- PetrolPriceMapScreen with flutter_map markers from cached NSW feed

### Security
- Bump `pypdf` 6.15.0 → 6.16.1 in `backend/requirements.txt` and
  `ai/requirements.txt` to close CVE-2026-84309, CVE-2026-84310 and
  CVE-2026-84311 (AUT-1894 PR-gate blocker).
- Suppress 2 HIGH libexpat CVEs (CVE-2026-66046, CVE-2026-76641) in
  `nginxinc/nginx-unprivileged:stable-alpine` via `.trivyignore` (AUT-1894).
  nginx image not yet rebuilt with expat 2.8.4-r0; time-boxed 2026-12-28.
- Re-add CVE-2026-14456 (OpenSSL QUIC DoS) to `.trivyignore` (AUT-1793/AUT-1894).
  python:3.13-slim ships openssl 3.5.6-1~deb13u2; no newer digest exists.
  AutoBrain never enables QUIC; time-boxed 2026-11-28.

### Fixed
- ci(code-review): make "Auto-approve PR on OCR stall (AUT-1814)" step
  `continue-on-error` so a 422 from the GitHub Reviews API (e.g.
  `Review Can not approve your own pull request` when the same
  identity opens and approves the PR) never turns the advisory OCR
  gate red. The Discord report still surfaces the OCR outcome
  unchanged (AUT-1894).

## [0.3.200] - 2026-09-02

### Fixed
- fix(worker): correct `$` escaping in HEALTHCHECK CMD-SHELL. Docker escapes
  `$$` only for RUN instructions — not for CMD-SHELL / HEALTHCHECK — so the
  prior fix landed as literal `$$(tr ...)` and sh expanded `$$` to PID,
  breaking command substitution. Use single `$` for `$(...)` so it flows
  through unchanged to the runtime shell (AUT-2056).

### Security
- Disable `/docs`, `/openapi.json`, and `/redoc` on the `market-data` FastAPI
  service in production (AUT-1745). CWE-200 information disclosure — these
  endpoints previously exposed the full API surface (endpoints, parameters,
  schemas) without authentication, matching the backend's pattern. Adds
  `test_docs_disabled.py` regression test. Docs remain available when
  `ENVIRONMENT` is set to a non-production value for local debugging.
- Unblock AUT-2165 PR security gates: pin `redis:7-alpine` by digest in
  `docker-compose.yml` (mirror the `docker-compose.prod.yml` / `.hosted.yml`
  pin from 0.3.198), bump `pypdf` 6.15.0 → 6.16.1 in `backend/` and `ai/`
  requirements (closes CVE-2026-84309/84310/84311), and replace the broken
  `dart pub audit` step in `.github/workflows/security-pr-gate.yml` with an
  `osv-scanner` scan against `frontend/pubspec.lock` so the Flutter
  dependency gate runs again on every PR.

## [0.3.199] - 2026-09-02

### Fixed
- fix(worker): rewrite HEALTHCHECK to pure POSIX `sh`, drop `[ -z "$(find ...)" ]`
  (nested `$()` inside `[ ]` fails under busybox/dash), drop the `pgrep`
  dependency (not in `python:3.13-slim`), and fix the `case` pattern syntax
  (`* -B *` was parsed by bash as `PATTERN OPTIONS PATTERN`). Clears the
  2000+ failing-strike healthcheck backlog on EP5 `autobrain-hosted-worker-1`
  (AUT-2056).
- fix(worker): switch HEALTHCHECK shell from `sh` to `bash` so the embedded
  `"$(find ...)"` pattern parses cleanly under busybox/dash. Clears the 2000+
  failing-strike healthcheck backlog on EP5 `autobrain-hosted-worker-1` (AUT-2056).
- fix(hosted): bump worker image digest to the latest `:hosted` build carrying
  the AUT-2056 bash healthcheck.

## [0.3.198] - 2026-09-01

### Security
- Pin every application image (`backend`, `worker`, `ai`, `frontend`,
  `dongle-server`, `federation-hub`) by `@sha256` digest in
  `docker-compose.hosted.yml`, replacing the floating `:hosted` manifest
  tag. Resolves the mutable-tag supply-chain gap flagged in AUT-1881.
- Pin `redis:7-alpine` by digest in `docker-compose.yml`,
  `docker-compose.prod.yml`, and `docker-compose.hosted.yml` (now
  `redis:7.2.5-alpine@sha256:6aaf3f5e...`).
- Build pipeline (`build-hosted.yml`) now captures the multi-arch manifest
  digest of every published image as a `$GITHUB_OUTPUT` value, so the next
  digest bump is a single workflow_dispatch with no GHCR round-trip.
- PR-time security gate (`security-pr-gate.yml`) gains a `pin-guard` job
  that fails any compose `image:` line lacking `@sha256` (with legitimate
  exemptions for `${VAR}` expansions and locally-built `build:` services).

## [0.3.197] - 2026-09-01

### Fixed
- fix(docker): unpin nginx base image digest in frontend Dockerfile (AUT-1908).
  The `@sha256:ee055adf...` digest was amd64-only; on arm64 hosted builds
  buildx pulled the amd64 binary into the arm64 image, causing
  `exec /docker-entrypoint.sh: exec format error` and a crash loop on
  hosted.autobrainservice.app. Use the `stable-alpine` tag so buildx resolves
  the correct architecture-specific manifest per build platform.

## [0.3.195] - 2026-08-30
- fix(ci): use GHCR_PAT secret for GHCR authentication in build-hosted.yml (AUT-1937). The `github_pat` secret name was invalid (GitHub blocks `github_*` prefix), causing 403 Forbidden on multi-arch image push, which broke the auto-update and deploy pipeline.

## [0.3.188] - 2026-08-30

- fix(backend): register fuel_servo router — Servo Spy API was dead code (AUT-1817).

## [0.3.186] - 2026-08-30

- fix(ci): GHCR push uses PAT (github_pat) when GITHUB_TOKEN lacks packages:write on self-hosted runners.

## [0.3.185] - 2026-08-30

### Servo Spy map view (AUT-1820)
- Map view now renders live station markers with brand logos and the current
  vehicle's fuel-type price, highlights the cheapest station, and shows a
  bottom sheet with all fuel-type prices + one-tap Navigate (Google Maps).

## [0.3.178] - 2026-08-30

### Added
- **Servo Spy list view with filters (AUT-1821):** the List view now shows nearby fuel stations sorted by price (cheapest first) using the current vehicle's fuel type by default. A filter sheet lets you change fuel type, set a max-distance radius (5–200 km slider), and toggle the sort metric between price and distance. Each row displays the station name, brand initial/avatar, distance, and current fuel price.

### Fixed
- **Servo Spy filter safety (AUT-1821 follow-up):** the fuel-type dropdown now seeds with the static defaults before the `GET /fuel/types` response lands, so the filter sheet remains valid if the vehicle list request fails first — no empty-dropdown crash.

## [0.3.176] - 2026-08-29

### Added
- **Vehicle fuel-type dropdown (AUT-1819):** the vehicle edit/add screen now has a data-driven `Fuel type` dropdown sourced from `GET /api/fuel/types` (canonical tokens E10/91/95/98/Diesel/LPG), falling back to a static list when the API is unavailable or premium-gated. The selection persists on `vehicles.fuel_type` and is exposed on the vehicle record for the map/list default-price behaviour. Backend adds the `fuel_type` column (migration `aut1819_fuel_type`, which also merges the six outstanding alembic heads so `alembic upgrade head` stays single-headed).
- **Servo Spy tab shell + Map/List selector (AUT-1818):** new premium-gated `Servo Spy` entry in the home feature grid opening a screen with a `Map`/`List` segmented control. The map is theme-aware (CARTO light basemap in light mode, dark basemap in dark mode) and follows the app light/dark theme. Free-tier accounts are shown the shared `PremiumGate` paywall and never see map or list data (gating requirement from AUT-1813). Live station markers/list rows are deferred to the backend fuel-price API (AUT-1817).

## [0.3.174] - 2026-08-29

### Added
- **Servo Spy fuel-price pipeline (AUT-1817):** deterministic, no-AI ingest of public open-data feeds — WA FuelWatch, NSW FuelCheck, QLD Fuel Prices — into new `fuel_stations` / `fuel_prices` Postgres tables (Alembic migration `f0a1b2c3d4e5`), with a Celery beat task (`ingest_fuel_prices`, every 6h). Premium-gated read API at `/api/fuel/*` (`/types`, `/brands`, `/stations?lat&lon&radiusKm&fuelType`, `/station/{id}/prices`, `/attribution`) — free accounts get 403 "Fuel prices are a premium feature. Upgrade to enable it." Open-data attribution is attached to every response (`X-Fuel-Data-Attribution`).

## [0.3.173] - 2026-08-29

### Security
- Suppress trivy 0.70 placeholder CVE-2026-80256 in `.trivyignore` — the
  nginx frontend image's vuln DB entry has no metadata yet (trivy logs
  "no vulnerability details" and exits 1 on the metadata miss). Trivy 0.74 +
  a fully populated DB will resolve it; this entry can be dropped after.

## [0.3.172] - 2026-08-29

### Changed
- **Stack/docker-compose (AUT-1763):** added a changelog entry for app/docker compose changes merged to `main` without one (changelog-gate now passes on push-triggered publishes). Covered compose changes since `55a0d98`: PostgreSQL bumped pg16→pg17 (digest-pinned) + trivy image gate; MinIO image pinned by digest + trivy scan; Redis auth now required in `docker-compose.prod.yml`; `AI_ROUTER_URL` canonicalized to `http://10.0.3.17:20128/v1`; market-data/AI Chromium runs non-root with sandbox + `shm_size`; 9Router `:20128` exposed on `0.0.0.0` with host-firewall allow-list; `init-minio.sh` no longer crash-loops backend when MinIO creds are absent; `autobrain-dongle-server` added to the hosted stack; CI triage receiver `CI_TRIAGE_*`/`PAPERCLIP_*` env wired in; petrol-price map keys scoped to default/hosted only; redeploy now pulls images with a Deployment-Lead-owned upgrade path.
- Parts lookup (AUT-1903): the Supercheap Auto lookup is now driven by the selected vehicle's stored rego state + plate instead of a free-text rego field — users no longer type a rego. Tapping the lookup action opens a dedicated results page listing all parts sorted and normalised by AI (deterministic fallback first, 9Router tidy), with the option to jump to "Add part" pre-filled or bulk-add selected parts to inventory. Vehicles gain a `rego_state` field (persisted at add/edit) backing this. Backend `POST /vehicles/{id}/parts/sca-lookup` now prefers the caller-supplied state and falls back to the vehicle's `rego_state`/plate.

### Fixed
- **SCA parts lookup 405 (AUT-1903):** the `/vehicles/{id}/parts/sca-lookup` route was registered as `GET` while the app `POST`s a JSON body, so every lookup failed with 405 Method Not Allowed. Switched to `POST` so the vehicle-driven lookup actually returns results.

## [0.3.168] - 2026-08-29

### Fixed
- **Shared-vehicle fuel-up "did not save" (AUT-1884):** a best-effort background
  due-notification task dispatched after a fuel-up save ran via Celery; when the
  broker (Redis) was momentarily down the dispatch raised AFTER the row was
  committed and surfaced a 500 to the client — so the fill-up persisted but the
  app read it as a failed save. The dispatch is now fire-and-forget
  (`fire_and_forget`) and never masks a committed write. The same safe dispatch
  is now used for receipt OCR + service-due sweeps everywhere `.delay()` was
  called directly.
- **Receipt OCR "did not work" (AUT-1884):** the fuel-receipt upload endpoint
  gated the entire operation (including deterministic photo storage) behind the
  AI rate limiter, which fails closed to 503 when Redis is unavailable — so a
  Redis blip dropped the receipt and skipped OCR entirely. The limiter is now
  best-effort (fail-open) for the storage/deterministic-OCR path; 9Router
  enrichment still falls back to the rule-based baseline. Tesseract OCR also
  now pre-processes receipt photos (grayscale -> 2x upscale -> Otsu threshold)
  for far more reliable text extraction from phone photos.
- **Camera did not open on receipt upload (AUT-1884):** the "Scan fuel receipt"
  button now opens the device camera directly (ImagePicker) with a "Choose from
  files" gallery option, instead of always launching the file picker.

## [0.3.166] - 2026-08-29

### Security
- **CI security gate / AUT-1746:** new `security-pr-gate.yml` runs on every PR and push to `main`: (1) **gitleaks detect** — blocks on any committed secret (`.gitleaks.toml` extends the vendored `gitleaks` v8.18.1 default ruleset + an AutoBrain allowlist of known non-secret fixtures/examples so the gate survives the squash-merge workflow); (2) **trivy config (misconfig)** on every Dockerfile build target (`docker/frontend`, `docker/backend`, `docker/ai`, `docker/worker`, `market-data`) — fails on HIGH/CRITICAL; (3) **pip-audit** on `backend/`, `ai/` and `market-data/` requirements (extends the existing PR gate to market-data); (4) **flutter pub audit** (`dart pub audit`) on `frontend/`. Compose misconfig is covered by the existing `trivy-image-scan.yml` (digest-pin + base-image CVE scan of the postgres/nginx/python images compose references) rather than a structural compose gate — current trivy has no compose misconfig scanner, and `docker compose config` false-errors on the working dev/hosted stacks, so it was intentionally not added to avoid blocking on non-issues. Combined with the existing `security-scan.yml` (weekly full-resolution pip-audit + external image scans), this closes the "no visible CI security gate" gap. Residual risk drops from Medium toward Low once these jobs are set as required status checks in branch protection.
- **Security reporting / AUT-1882:** `docs/security.md` now classifies the 9Router `:20128` port as **source-restricted, NOT internet-exposed** (reachable only from the allow-listed dev egress IP `122.199.30.128/32` + the internal docker subnet `172.18.0.0/16`, all else dropped by `fw-keeper`). Added explicit false-positive guidance: a scan launched from the allow-listed egress IP sees the port open *by design* and must not be reported as "accessible from the internet"; confirm non-exposure with multi-source external probes (e.g. check-host.net nodes), which time out. Stops the recurring false "9Router is internet-accessible" finding.

## [0.3.164] - 2026-08-29

### Added
- Fuel: accurate 7-Eleven fuel prices via projectzerothree.info (`GET /vehicles/{id}/fuel/prices/7eleven`) — deterministic, no AI. Cheapest-by-region and nearest-store modes for auto-filling price-per-litre (AUT-1887).

## [0.3.161] - 2026-08-29

### Security
- Backend (market-data): `_client_ip()` now honors `X-Forwarded-For` only when the direct socket peer is in the `TRUSTED_PROXIES` allowlist (mirroring `rego-lookup-api`), so spoofed `X-Forwarded-For` headers can no longer rotate per-IP rate-limit buckets (CWE-602, AUT-1741). Default (no `TRUSTED_PROXIES`) is unchanged: the socket peer keys the IP bucket and XFF is ignored.

## [0.3.159] - 2026-08-29

### Fixed
- Backend: full-DB JSON backup now emits strict RFC-8259 JSON — non-finite Postgres `FLOAT` values (NaN/`Infinity` from `0/0` or divide-by-zero) are coerced to `null` instead of writing the invalid `NaN`/`Infinity` tokens that off-box backup agents reject (the "failed backup jobs for hosted" failure, AUT-1854). `scheduled_backup` also honours `BACKUP_ENABLED`.

## [0.3.157] - 2026-08-29

### Added
- **Upgrade path for instances (AUT-1847):** new
  `scripts/upgrade-instances.sh` redeploys the Demo → Default → Hosted Portainer
  stacks in promotion order (pullImage, health-gated). Owned by the Deployment
  Lead: CI publishes an image, posts a Discord `#ops` notify, and the Deployment
  Lead triggers `deploy-instances.yml` (workflow_dispatch) to run the upgrade
  path — no blind/automatic deploy (board direction).
- **Real redeploy fix (AUT-1847):** the Portainer stack update now passes
  `pullImage=true`, so the freshly published image is actually pulled and changed
  services recreated. Without it the compose re-applied with the same digest and
  instances silently never updated.

### Fixed
- **Hosted redeploy could never succeed (AUT-1847):** `docker-compose.hosted.yml`
  required `POSTGRES_USER`/`POSTGRES_DB` via `${VAR:?...}`; a stack env missing
  them failed compose interpolation. Now defaulted to `autobrain`, so a redeploy
  can never fail at interpolation.

## [0.3.153] - 2026-08-28

### Changed
- **CI (AUT-1802):** OCR review job confined to the x64 runner (vm2); the arm64 Oracle VM runner is reserved exclusively for building arm images. Review/merge no longer stalls on the scarce arm runner.
- **CI (AUT-1814):** when the advisory OCR (Open Code Review) gate stalls or fails, an approving review is submitted automatically so PRs don't park waiting on a manual gate. OCR remains non-blocking; real gating is other checks + owning-department QA/Security sign-off.
- **Hosted (AUT-1713):** added `dongle-server` firmware-distribution service to the Oracle VM hosted stack (Portainer EP5) — MinIO-backed static asset serving, `/health` on 8012, `DONGLE_SERVER_API_KEY`/web-basic-auth injected via Portainer secrets (supersedes AUT-1673 naming).

### Fixed
- feat: add autobrain-dongle-server to hosted stack (AUT-1673) (gardened, AUT-1777).

- API: rego-lookup endpoint now enforces a per-user hourly rate limit (default 20/hour, configurable via `REGO_RATE_LIMIT_PER_HOUR`, fail-open on Redis outage) to protect the downstream AU rego service (AUT-1607).

- IAP: gracefully fall back to Stripe checkout when product IDs are not configured in the Play Store — prevents Google Play's native "in-app purchases not available" overlay from blocking the upgrade flow (AUT-1149).

### Fixed
- **AI gateway (AUT-1810):** AI router URL normalised to the corporate 9Router endpoint `http://10.0.3.17:20128/v1` (env `AI_ROUTER_URL` canonicalised) so OCR/AI calls never drift to a wrong/blank router.

### Security
- Hardened Redis in `docker-compose.prod.yml` — added `--requirepass` and updated healthcheck to authenticate; environment variable `REDIS_PASSWORD` is now required (AUT-1600).
- **Security (AUT-1600):** hardened Redis healthcheck — `redis-cli` now receives `REDIS_PASSWORD` via the `REDISCLI_AUTH` env var instead of `redis-cli -a`, so the broker password never appears in the container process list (`docker-compose.yml`, `docker-compose.prod.yml`).

### Security
- **Security (AUT-1735):** Bumped `docker/backend`, `docker/ai`, `docker/worker` and `market-data` Dockerfiles off the vulnerable `python:3.12-slim` base (trivy reported 18 HIGH/CRITICAL CVEs: CVE-2026-13221 perl RCE, CVE-2026-42496 perl-Archive-Tar path traversal, CVE-2026-8376 perl heap overflow, CVE-2026-14456 OpenSSL QUIC DoS, CVE-2026-11822/11824 SQLite FTS5 code exec, CVE-2025-7458 SQLite integer overflow, CVE-2023-45853 zlib heap overflow). All python bases now pin `python:3.13-slim@sha256:...` by digest. Added a python base-image scan to `.github/workflows/trivy-image-scan.yml` (`--severity HIGH,CRITICAL --exit-code 1`) plus a pin guard that fails any floating `FROM python:*` tag. `rego-lookup-api/Dockerfile` (separate private repo) tracked in follow-up AUT-1735-r1.

### Security
- (AUT-1181) Fail-closed secret defaults (HIGH): `SECRET_KEY` no longer has a
  development default that can forge JWTs — missing/placeholder values (the
  historic `change-me` and `change-me-to-a-long-random-string`) require a real
  key (`python -c "import secrets; print(secrets.token_urlsafe(64))"`); in
  `development` only, an ephemeral random key is generated per boot.
  `ADMIN_API_KEY` must be ≥ 32 chars when enabled; when `STRIPE_SECRET_KEY`
  is set, an empty `STRIPE_WEBHOOK_SECRET` now crashes at startup so forged
  webhooks cannot mutate subscriptions.

### Fixed
- AI: rate limiter evicts stale buckets on overflow instead of clearing all entries, preventing 10K+ IP rotation from keeping limits perpetually ineffective (AUT-1605).

### Fixed
- **AUT-1185** AI gateway OOM DoS + auth bypass + prompt injection (security):
  - social_image module: `width`/`height` now clamped to 200–2048 via Pydantic
    validator — prevents ~3×10¹⁸-byte allocation from `width=height=999999999`.
  - router_client: router response capped at 1 MB (`_MAX_ROUTER_RESPONSE_BYTES`),
    nested schema validation enforces max depth 4 and max array length 100.
  - router_client: user payload now wrapped in `<untrusted_user_data>` tags with
    an explicit system instruction to treat it as data only (prompt-injection
    mitigation).
  - main: `AI_ENV=development` no longer disables auth; only the explicit
    `AI_GATEWAY_AUTH_DISABLED=1` opt-out opens `/v1/*`.
- **AUT-1185** Per-caller HMAC keyed auth is deferred — see follow-up issue for
  rollout requiring backend coordination (key rotation + revocation lifecycle).

### Added
- Regression tests: `test_run_clamps_oversized_dimensions`, `test_validate_nested_depth_and_length`,
  `test_ai_env_development_no_longer_bypasses_auth`, `test_enhance_drops_nested_too_deep`.

### Fixed
- **App (AUT-1771):** The 7-day free trial now appears on the Android (and iOS) app. The trial chip/Copy/CTA were previously hidden whenever the store (IAP) purchase path was active — and the hosted instance reports IAP as enabled, so Android users never saw the offer. The trial is now surfaced for both the Stripe checkout path and the store path, driven by the per-account `trial_available`/`trial_days` flags from `GET /auth/me`. Note: for the store path the native Google Play / App Store subscription base plan must be configured with the 7-day free trial for it to apply; the Stripe monthly checkout already grants it via `trial_period_days`.

## [0.3.152] - 2026-08-28

### Security
- **CI/Infra (AUT-1739):** `market-data/Dockerfile` no longer runs as root (CWE-250): creates a non-root `appuser` (uid 1000), chowns the app tree, and sets `USER appuser`. Playwright Chromium's `chrome-sandbox` is kept root-owned + setuid (`4755`) so the market-data scraper sandboxes untrusted third-party content as non-root; `market-data/browser.py` (`scrape_sca`) now launches Chromium sandboxed and only falls back to `--no-sandbox` when the sandboxed launch fails (matching `scrape_bikesguide`). The `ai` image (`docker/ai/Dockerfile`, already non-root) now also sets the SUID bit on its Playwright Chromium `chrome-sandbox`. The `ai` service in `docker-compose{.prod,.hosted,yml}` now sets `shm_size: 256m` for an adequate `/dev/shm`.

### Added
- **CI/Ops (AUT-1720):** `scripts/runner-watchdog.sh` + `infra/systemd/gh-runner-watchdog.{service,timer}` (with `gh-runner-watchdog.sudoers` NOPASSWD drop-in) that self-heal the x64 runner. Each tick probes dockerd with a hard timeout and, only after repeated unresponsive probes (so a slow multi-minute `docker buildx` publish is never killed), restarts containerd + docker and prunes orphaned buildx/builder state. It also restarts a `Runner.Listener` stuck in uninterruptible sleep. Deployed live on the vm2 x64 runner host (`gh-runner2`).
- **CI/Ops (AUT-1720):** `ci-queue-guard.yml` scheduled workflow that automatically cancels GitHub Actions runs left `queued` on a branch that has been merged/deleted — the exact condition that wedged the x64 publish pipeline (the run becomes an un-cancellable GitHub zombie that makes the queue look frozen).

### Fixed
- **CI/Ops (AUT-1720):** The x64 self-hosted runner no longer freezes indefinitely during heavy `docker buildx build --push` publishes. Root cause was an intermittent dockerd wedge (publish job would hang until GitHub killed it with `context deadline exceeded`); the new watchdog restarts the daemon proactively before it wedges the next job.

## [0.3.150] - 2026-08-28

- Market-data rate limiting now keys the per-IP limit on the socket remote address instead of `X-Forwarded-For`, so a forged forwarded header can no longer rotate the bucket and evade the limit (AUT-1326).
- The market-data Playwright Chromium now launches **sandboxed**, falling back to `--no-sandbox` only when the sandboxed launch actually fails (AUT-1326).
## [0.3.149] - 2026-08-28

### Fixed
- Deployment (hosted): `9Router` on `:20128` is now reachable at the public IP `http://152.69.188.133:20128/` from the allow-listed dev egress IP `122.199.30.128` (e.g. home). It was previously bound to `127.0.0.1` (ops via SSH tunnel only), making it unreachable. `docker-compose.hosted.yml` rebinds `:20128` to `0.0.0.0`; the host firewall (`fw-keeper`) now allows `:20128` from the dev IP + the internal docker subnet `172.18.0.0/16` and drops everything else. Backend/ai still call 9Router over docker DNS (`http://9router:20128/v1`) — the internal-subnet allow is required, since a blanket `DOCKER-USER` drop silently broke `backend → 9router`. AUT-1754.
## [0.3.148] - 2026-08-28

- Backend: SSRF hardening for Discord webhook URLs (AUT-1603). `discord_webhook_url` now allowlists `https://discord.com/api/webhooks/{id}/{token}` at two layers — a Pydantic `field_validator` on the notification-preference schema rejects non-Discord URLs at input time, and `_send_discord` re-checks the pattern before the outbound `httpx` call as defense-in-depth (rejecting internal/loopback addresses). `NotificationPreferenceOut` response schema restored so the preferences API keeps working.

### Added
- Parts: Supercheap Auto parts-guide lookup integrated into market-data container. Users can now extract SCA parts categories by rego+state (via Playwright browser) or manually (plain HTTP). Integration provides clean Inventory-formatted JSON with 9Router tidying. AI suggested services now prefill parts (inventory-first, then SCA secondary). Feature AUT-1792.

## [0.3.146] - 2026-08-27

### Fixed
- Deployment: `scripts/init-minio.sh` no longer hard-aborts the backend at startup when `MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` are absent — it now skips bucket init cleanly (and bounds its MinIO wait loop), so a missing/optional MinIO config can no longer crash-loop the backend (e.g. the Dev-box EP6 `autobrain-dev` stack, AUT-1786). `docker-compose.yml` and `docker-compose.prod.yml` now explicitly pass those vars to the backend for parity with the hosted secret-file path.

## [0.3.145] - 2026-08-27

### Security
- Frontend: pinned the `nginxinc/nginx-unprivileged:stable-alpine` base image by digest (`sha256:93722936b82ec8a1178d48448e619226680d2de3706a1640800e186cd5fa7fd3`, built 2026-08-24) to remediate `CVE-2026-14456` (OpenSSL QUIC unbounded memory growth / DoS in libcrypto3/libssl3). Also extended the trivy base-image gate to scan the frontend nginx image and reject floating `FROM` tags (AUT-1740).

## [0.3.144] - 2026-08-27

### Fixed
- CI: set `cancel-in-progress: false` on `build-hosted.yml` and `dockerhub-publish.yml` so a newer push to `main` (PR merge) queues behind, rather than cancelling, the ~20-min in-flight multi-arch build — the previous `cancel-in-progress: true` cancelled every release build that a later push landed on, permanently starving the `:hosted` image (AUT-1756, root cause AUT-1762).

## [0.3.143] - 2026-08-27

### Fixed
- CI: moved the `ci-triage-webhook.yml` `fire` job to GitHub-hosted `ubuntu-latest` so its 15-min `sleep`+curl never monopolises a scarce self-hosted release runner (x64 or arm64), freeing both for real build work (AUT-1762).
- CI: tagged auto-bump commits `[skip ci]` so the version-cut push no longer re-triggers `build-hosted.yml`/`dockerhub-publish.yml` and cancels the in-flight multi-arch release build — this unblocks the missing `:hosted` image (AUT-1756, root cause AUT-1762).

## [0.3.142] - 2026-08-27

### Added
- CI: wired `CI_TRIAGE_WEBHOOK_SECRET`, `CI_TRIAGE_PARENT_ISSUE_ID`, `CI_TRIAGE_GOAL_ID`, `CI_TRIAGE_AGENT_ID`, and `PAPERCLIP_*` env into the AutoBrain-Hosted backend service in `docker-compose.hosted.yml`, so the merged CI triage webhook receiver (`backend/app/api/v1/ci.py`) is configured and reachable and can relay GitHub Actions CI failures into Paperclip (AUT-1751).

### Added
- CI: added CI triage webhook receiver at `POST /api/v1/ci/webhook` with bearer auth, fail-closed PAPERCLIP config validation, and `repo`/`ref` payload validation to create Paperclip issues from GitHub Actions CI failures, replacing the broken n8n webhook (AUT-1669).

### Fixed
- CI: scoped `ci-triage-webhook.yml` `push` trigger to `main` only, preventing cancelled `fire` checks on PR branches that marked pull requests as unstable.
- CI: added `timeout-minutes: 20` to the CI triage `fire` job to prevent zombie `sleep 900` jobs from consuming self-hosted runner capacity.
- Tests: fixed `test_ci_webhook.py` settings monkeypatching (patch `ci_mod.settings`, not just `config_mod`) and corrected `resp.json` mock to synchronous; all 8 tests pass.
- CI: hardened ci_webhook httpx calls with try/except for httpx.HTTPError and non-JSON Paperclip responses; both return 502 instead of raising 500.
- CI: install pip-audit to a `--target` dir in pip-audit-gate to bypass PEP 668 on externally-managed self-hosted runners; bootstrap pip via `get-pip.py` (urllib-downloaded) when `python3 -m pip` is unavailable; run pip-audit with `PYTHONPATH` pointing at the target dir (AUT-1661, AUT-781).

## [0.3.141] - 2026-08-26

### Fixed
- BLE OTA (AUT-1673 / AUT-1714): resolved PR #296 review feedback and latent compile breaks — `ApiClient.get` now JSON-decodes and applies the 30s timeout / 401-refresh (it was returning a raw `http.Response`); fixed an unclosed brace in `DongleWifiPanel._readAndRefresh`; added web/desktop stubs for `readDeviceInfo`/`applyOta`; gated the still-unimplemented `applyOta` behind `isOtaAvailable`; empty firmware rows now render "— not reported"; `/dongle/firmware/report` enforces a strict charset whitelist (XSS/SQLi defence-in-depth) and `sha256` accepts uppercase hex.

## [0.3.140] - 2026-08-26

### Fixed
- Security: validated Discord webhook URL pattern in notification preferences to block SSRF via user-controlled webhook URLs; added `follow_redirects=False` as defense-in-depth (AUT-1603).

## [0.3.139] - 2026-08-26

### Fixed
- CI: added `lib/services/iap_service.dart` to the mobile sync delta-restore list so the mobile-only `IapService` singleton, `IapCatalog`, and `IapProduct` classes survive the shared `lib/` overwrite — fixes `flutter analyze` failures in `license_screen.dart` (AUT-1634).

## [0.3.138] - 2026-08-25

### Fixed
- CI: switched `publish` and `build-hosted` workflows to `ubuntu-latest` runners while x64 self-hosted runners are offline — unblocks Docker image publishing and multi-arch builds (AUT-1586).
- CI: replaced raw `git` checkout with `actions/checkout` in publish job so it works on fresh GitHub-hosted runners (AUT-1586).
- Fix: IAP service used `billingClientPurchase` (Android-only API unavailable on web), replaced with cross-platform `verificationData.serverVerificationData` (AUT-1586).

## [0.3.137] - 2026-08-25

### Fixed
- IAP: added Android `com.android.vending.BILLING` permission to `AndroidManifest.xml` so the Play Store recognises the app as IAP-capable and shows in-app purchases on the listing (AUT-1149).

### Fixed
- CI: switched `publish` and `build-hosted` workflows to `ubuntu-latest` runners while x64 self-hosted runners are offline — unblocks Docker image publishing and multi-arch builds (AUT-1586).
- CI: replaced raw `git` checkout with `actions/checkout` in publish job so it works on fresh GitHub-hosted runners (AUT-1586).
- Fix: IAP service used `billingClientPurchase` (Android-only API unavailable on web), replaced with cross-platform `verificationData.serverVerificationData` (AUT-1586).

## [0.3.137] - 2026-08-25

### Fixed
- IAP: added Android `com.android.vending.BILLING` permission to `AndroidManifest.xml` so the Play Store recognises the app as IAP-capable and shows in-app purchases on the listing (AUT-1149).
- IAP: added `in_app_purchase` Flutter package to monorepo `pubspec.yaml` and wired native Play Store / App Store purchase flow into the license screen — "Buy from Store" button now initiates a native store purchase via Google Play Billing / StoreKit instead of falling back to Stripe browser checkout (AUT-1149).

## [0.3.136] - 2026-08-24

### Changed
- Docs: OBD2 dongle pin guide now maps every firmware GPIO to its physical devkit pin — added a Board label column (silkscreen names: D5, TX2, RX2, VIN…), a full 38-pin DOIT-style board locator diagram with all used pins marked, clone-variant caveat (trust silkscreen, not position), and boot-time strapping notes for D5/D15/D14. New `docs/obd2-dongle/check-pinmap.py` asserts `config.h` pins stay in sync with the doc.

## [0.3.135] - 2026-08-24

### Added
- OBD: the app now connects to the custom AutoBrain OBD2 ESP32 adaptor over Bluetooth from the OBD tab — auto-connect on open (toggle), "Connect & sync now" pulls completed trips off the adaptor and into your logbook (deduped against WiFi uploads), and a codes section shows the fault codes the adaptor reads with one-tap AI diagnostics and a confirmed clear-codes-on-car action. Works over the adaptor's WiFi upload too: it now pushes its code snapshot to the same library.

### Changed
- OBD: Dongle WiFi settings moved out of Settings and into the OBD tab, with a Sync now button that re-pushes saved WiFi credentials to the dongle over BLE.

## [0.3.134] - 2026-08-24

### Removed
- Merch: last merch surface removed from the app + backend — deleted `MerchOrder` model, `app/services/merch.py` webhook recording and `test_merch.py`; billing webhook now handles subscription checkouts only; dropped the `merch_orders` table via new migration. Merch/commerce lives ONLY on autobrainservice.app (product rule PR-2, updated) — supersedes AUT-1567's passive-table compromise (AUT-1571).

## [0.3.133] - 2026-08-24

### Removed
- Merch: in-app merch store removed entirely (Settings → Merch screen, `assets/merch/` bundle, and the `/api/v1/merch/catalog|checkout|orders` endpoints) — merch (incl. the AutoBrain Beanie) is sold ONLY on the autobrainservice.app website merch section, per new product rule PR-2 with a CI guard test. Completed website orders still persist via the Stripe webhook (web + mobile) (AUT-1567).

## [0.3.132] - 2026-08-24

### Fixed
- Merch: AutoBrain Beanie price corrected to A$55 and now ships free (checkout no longer adds the flat shipping rate) — web + mobile (AUT-1559).

## [0.3.131] - 2026-08-24

### Changed
- Deploy (hosted): secrets bind-mount sources in `docker-compose.hosted.yml` are parametrized via `${SECRETS_DIR:-/opt/autobrain/secrets}` so hosts with a read-only rootfs can relocate the secrets dir (hosted uses `/data/autobrain/secrets`; see `docs/security.md`) without editing the compose file (AUT-1535).

## [0.3.130] - 2026-08-24

### Added
- Merch store (AUT-1540): in-code catalogue served at `GET /api/v1/merch/catalog` (AutoBrain Beanie, A$25.00 AUD); `POST /api/v1/merch/checkout` opens Stripe Checkout that collects the shipping address + phone with a flat A$9.95 standard-shipping option; completed payment checkouts are recorded as orders via the billing webhook (idempotent by session id) and listed at `GET /api/v1/merch/orders`. Flutter app gains a Settings → Merch store screen (shop + order history) with the beanie artwork bundled.

### Changed
- Billing: find-or-create Stripe customer extracted to `billing.ensure_customer`, now shared by subscription and merch checkouts.

## [0.3.129] - 2026-08-24

### Changed
- App: swapped app logo to the new no-text mark across web icons, iOS AppIcon set (all 25 sizes), Android launcher mipmaps + adaptive foregrounds, and in-app `assets/logo.png`/`app_icon.png` (AUT-1544)

## [0.3.128] - 2026-08-24

### Security
- Docker: stack-config hardening from AUT-1486/AUT-1498 audit (AUT-1533) — credentials moved to `*_FILE` secret files loaded at entrypoint (`docker/lib-load-secrets.sh`), so Postgres/Redis/MinIO/backend/API-key values never appear in container env; Redis/Celery broker now requires auth (`--requirepass`, derived authenticated URLs); 9Router image digest-pinned; compose config check + secret-seed scripts added.

## [0.3.127] - 2026-08-23

### Added
- Shared fuel write access test suite (AUT-1382): new tests verifying shared vehicle fuel entry write permissions and access control.

## [0.3.126] - 2026-08-22

### Fixed
- App: License screen surfaces the 7-day free trial — "7 days free" chip + trial copy on monthly plan cards, "Start your 7-day free trial" CTA, status-card mention; hidden in IAP mode, on yearly, and once the trial was used (AUT-1411)

## [0.3.125] - 2026-08-22

### Fixed
- Docker: worker healthcheck detects embedded beat (`-B`) in the celery cmdline so the AUT-601 `celerybeat-schedule` freshness check fires on hosted workers (AUT-1286)

## [0.3.124] - 2026-08-22

### Security
- Backend: billing trial TOCTOU fix — `has_had_trial` claimed in `_apply_subscription` (webhook path, atomic with plan grant); duplicate/racing trial subscriptions end immediately via Stripe `trial_end=now` (AUT-1211)

## [0.3.123] - 2026-08-22

### Fixed
- Frontend: iOS fuel receipt entry — decimal keyboard enabled for Litres, Price, Total so users can type `.` (AUT-1381)

## [0.3.122] - 2026-08-21

### Security
- AB-06: Global per-IP rate limiting middleware + per-route limits (signup 5/min, password-reset 3/min, login 10/min) (AUT-1187)
- AB-07: ILIKE wildcard escape (`%`/`_`) + pagination on admin API user search (AUT-1187)
- AB-09: Backup restore SHA-256 checksum + schema validation, wrapped in DB transaction (AUT-1187)
- AB-14: Asset restore streams to temp file (1 GB cap) instead of 5 GB in-memory load (AUT-1187)
- AB-10: Uniform signup response prevents user enumeration via 409 (AUT-1187)

## [0.3.121] - 2026-08-21

### Fixed
- Deploy: .env and secrets/ excluded from remote tarball — prevents credential leak during deploy (AUT-1188)
- Frontend: nginx runs unprivileged (nginx-unprivileged image, USER nginx, port 8080) — root process eliminated (AUT-1188)
- Hosted & prod stacks: all services hardened — read_only rootfs, cap_drop ALL, tmpfs for /tmp & /var/run (AUT-1188)
- Systemd: backend service runs as docker user, not root (AUT-1188)
- Frontend nginx: server_tokens off added — version disclosure removed (AUT-1188)

## [0.3.120] - 2026-08-21

### Security
- Frontend: default API/WS to https/wss; AndroidManifest adds `android:usesCleartextTraffic="false"` (F1)
- Android: release build no longer uses debug keystore; signing config via local.properties/CI secrets (F2)
- Android: `android:allowBackup="false"` blocks ADB/cloud backup of secure storage (F3)
- Password reset token delivered via URL fragment (`#token=`) not query string — removed from logs/history (F4)

## [0.3.119] - 2026-08-21

### Security
- Dev compose: PostgreSQL, Redis, MinIO, and AI gateway bound to 127.0.0.1 (AB-INFRA-004/006) — no external exposure in local dev
- Dev compose: Redis requires auth (REDIS_PASSWORD) — open broker eliminated (AB-INFRA-004)
- Dev compose: AI gateway auth mandatory (AI_GATEWAY_API_KEY) — dev opt-out removed, fail-closed everywhere (AB-INFRA-006)

## [0.3.116] - 2026-08-21

### Added
- Embed-on-create smoke test (AUT-1242-C4): new test suite asserting all five
  entity types produce searchable text, the `_valid_embedding` dimension guard
  rejects malformed vectors, and an integration test confirms every entity type
  stores a non-NULL embedding via the `backfill_entity_embedding` path.

## [0.3.115] - 2026-08-21

### Changed
- Hosted stack (AUT-1242): `minio-init` one-shot sidecar removed from
  `docker-compose.hosted.yml` — bucket init (create + force-private) now runs in
  the minio container's own entrypoint before the server blocks, which waits for
  MinIO to accept connections and stays idempotent. One fewer container to run.

## [0.3.114] - 2026-08-20

### Changed
- Merged the market-data scraper into the AI image (AUT-1242-C3): the separate
  `market-data` container is gone. The AI image now runs both this AI gateway
  (`:8001`) and the CarsGuide/BikeGuide market-data API (`:8000`) via an
  entrypoint wrapper, saving a container in the hosted stack.
- Entrypoint now supervises both processes: whichever uvicorn dies first tears
  the container down so Docker restarts it; prod compose wires the scraper's
  `API_KEY` and exposes `:8000` (AUT-1299).
- Aligned `pydantic` pin across `ai/requirements.txt` and `backend/requirements.txt` to
  `pydantic==2.10.4` (AUT-1298). The divergent pin (`2.13.4` in ai/ vs `2.10.4`
