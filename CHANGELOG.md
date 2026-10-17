# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.

## [Unreleased]
### Added (AUT-6519)
- docs: add secret-file-pattern.md documenting AUT-1533 *_FILE secret injection pattern for docker-compose (AUT-6519)

### Fixed (AUT-6431)
- fix(build): add archive dependency override to fix Dart compile failure (AUT-6431)

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

### Removed (AUT-5718)
- Removed the dead `POST /api/v1/ci/webhook` CI triage receiver. The GitHub Actions `ci-triage-webhook.yml` fire job has never posted to the AutoBrain backend — it fires `secrets.CI_TRIAGE_WEBHOOK_URL`, the Paperclip routine trigger on the `CI Triage` routine, and that routine trigger is the only thing that wakes the CI Triage Agent. The backend route had no callers: AutoBrain-Hosted answered `503 CI triage webhook not configured` to every request since at least 2026-09-03 because `docker-compose.hosted.yml` wired `CI_TRIAGE_WEBHOOK_SECRET`/`CI_TRIAGE_PARENT_ISSUE_ID`/`CI_TRIAGE_GOAL_ID` to empty defaults the Hosted env file never set, and the Hosted access log contains no POST from any Actions runner to that path. Deletes `backend/app/api/v1/ci.py`, its router registration, the `CI_TRIAGE_*` + server-side `PAPERCLIP_*` settings in `backend/app/core/config.py`, the same block in `docker-compose.hosted.yml`, the `CI_TRIAGE_*` block in `.env.example`, and the `/ci/webhook` row in `docs/Engineering/api-spec.md`; `ci-triage-webhook.yml` and the deployment guide now state that the Paperclip routine trigger is the canonical receiver so the route is not re-added or repointed. The Hosted stack no longer needs `PAPERCLIP_API_KEY`/`CI_TRIAGE_WEBHOOK_SECRET` to boot. `backend/tests/test_ci_receiver_removed_aut5718.py` asserts the route is gone (404) and the settings no longer exist, so a re-added receiver fails CI.

### Fixed (AUT-4812)
- fix(backend): `tests/test_advisor_value.py` could not import `BAND_LOW_RATIO` / `BAND_HIGH_RATIO` from `app.services.advisor`, so the entire backend suite failed at collection — masked by `ci-tests.yml` running the suite as `pytest … || true`. The `app.services.advisor` package `__init__.py` already re-exports both constants from `advisor/value.py`; the stale `backend/app/services/advisor.py` module that shadowed the package is deleted (no imports referenced it). Removed `|| true` from the full-suite step in `.github/workflows/ci-tests.yml` so future collection errors fail the build. All 16 `test_advisor_value.py` tests pass; full suite collects without import errors.

### Fixed (AUT-5668)
- fix(ci): `ci-triage-webhook.yml` fire job was incorrectly pinned to the self-hosted vm2 runner (`runs-on: [self-hosted, linux, x64, vm2]`) despite comments explicitly stating it must run on `ubuntu-latest` to avoid consuming scarce self-hosted runners for 15-minute sleep+curl bursts. The misconfiguration caused the step to hang and be killed by the 20-minute timeout (AUT-5668), silently losing ~half of CI triage wakes. Changed `runs-on` to `ubuntu-latest` (timeout was already increased to 30 minutes).

### Fixed (AUT-5584)
- fix(frontend): `Sync mobile app` workflow failed on `main` with `lib/core/models/fuel_history.dart is not referenced by a part directive in lib/core/models.dart`. The monorepo `frontend/lib/core/models.dart` was missing the `part 'models/fuel_history.dart';` directive that `autobrain-mobile` PR #60 added to its models.dart. Added the missing `part` directive and the corresponding `fuel_history.dart` model file to the monorepo source-of-truth so the sync guard (AUT-5205) passes and the mobile tree stays in parity. Verified by re-running the `Sync mobile app` workflow.

### Changed (AUT-5654)
- ci: moved the last four GitHub-hosted jobs onto the self-hosted vm2 runners, finishing this repo's hosted-runner migration. `visual_regression.yml` (was `ubuntu-latest`) now runs on `[self-hosted, linux, x64, vm2]`; its `subosito/flutter-action@v2` step downloads the Flutter SDK itself, so no pre-installed toolchain is required on the runner. `dockerhub-publish.yml`'s `dedupe-main-queue`, `ci-queue-guard.yml`'s `cancel-orphaned-runs`, and `ci-triage-webhook.yml`'s `fire` also move to `[self-hosted, linux, x64, vm2]`: all three are API-only gates that call `gh api` to cancel superseded/orphaned runs and to fire the triage webhook, and none of them checks out or executes repository code, so they are safe on a persistent runner even under the `pull_request` trigger. `build-hosted.yml`'s matrix already resolved to vm2/ARM64 and is unchanged. After this, no workflow in this repo requests a GitHub-hosted runner.

### Fixed (AUT-5639)
- fix(backend): `GET /api/v1/advisor/replace` 500ed for every caller, and the next build of the backend could not boot at all. AUT-3916 (`389213ca`, Sep 26) deleted the legacy `backend/app/services/advisor.py` — which held `compute_replace` — and rewired `app/api/v1/advisor.py` to import it from the new `app.services.advisor` package, but the function was never moved into the package, so the package never exported it. The 500 stayed invisible for ~9 days because `ci-tests.yml` runs the suite as `pytest … || true` and `tests/test_advisor_replace.py` skips its route tests when `app.main` fails to import (they had never actually run: the module's fake vehicle had no `id` and `get_accessible_vehicle` was patched with a sync lambda, both now fixed). AUT-5639's PR #915 added the missing import line, which turned the latent breakage into a hard `ImportError` at boot for every process that imports `app.main` — i.e. main went red and any image built from it would crash-loop. This restores `compute_replace` in `app/services/advisor/replace.py` (verbatim from the deleted legacy module — deterministic, no AI/no network: used cost = current private-sale mid, new cost = mid × documented `new_used_premium(age)`, gap = replacement − current − trade-in mid, `surplus` on a non-positive gap) and re-exports it from `app/services/advisor/__init__.py`. `tests/test_advisor_replace.py` now runs instead of skipping (15 passed, 0 skipped; 834 tests collect clean) and pins the export with a new `test_compute_replace_is_exported`, so a future dropped export fails collection at CI time instead of in production.

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
