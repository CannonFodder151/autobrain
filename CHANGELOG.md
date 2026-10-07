# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.


## [Unreleased]

### Fixed (AUT-4812)
- fix(backend): `tests/test_advisor_value.py` could not import `BAND_LOW_RATIO` / `BAND_HIGH_RATIO` from `app.services.advisor`, so the entire backend suite failed at collection — masked by `ci-tests.yml` running the suite as `pytest … || true`. The `app.services.advisor` package `__init__.py` already re-exports both constants from `advisor/value.py`; the stale `backend/app/services/advisor.py` module that shadowed the package is deleted (no imports referenced it). Removed `|| true` from the full-suite step in `.github/workflows/ci-tests.yml` so future collection errors fail the build. All 16 `test_advisor_value.py` tests pass; full suite collects without import errors.

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

## [0.3.266] - 2026-09-11

### Security (AUT-2060)
- Bumped `python:3.13-slim` base image digest from `7ce4b6d...` to `cc9dffa...` (2026-08-31 Docker Hub latest) in `docker/backend/Dockerfile`, `docker/ai/Dockerfile`, `docker/worker/Dockerfile`, and `market-data/Dockerfile`. New digest ships `libssl3t64` 3.5.7-1~deb13u2, resolving CVE-2026-14456 (OpenSSL QUIC DoS) and related HIGH CVEs. Updated `PYTHON_BASE_IMAGE` env var in `.github/workflows/trivy-image-scan.yml`. Removed resolved CVE-2026-14456 suppression from `.trivyignore`.

### Added (AUT-3251)
- feat(backend,frontend): add `powertrain` field (ICE/HEV/PHEV/EV) to vehicle schemas, models, and add/edit screens — fixes missing EV feature wiring.

## [0.3.265] - 2026-09-11

### Fixed (AUT-2683)
- fix(frontend): fix login_screen.dart widget tree — remove premature Column close after logo Container, add missing inner Column children close, and fix closing bracket nesting (introduced by AUT-3219).

## [0.3.264] - 2026-09-11

### Fixed (AUT-3219)
- fix(frontend): migrate `connectivity_plus` to 6.x API (`Connectivity()` constructor, `result != ConnectivityResult.none`), replace deprecated `MediaQuery.withClampedTextScaling` with `MediaQuery.textScalerOf`, and fix Dart parse errors (unbalanced parentheses) in `signup_screen.dart`, `login_screen.dart`, `add_vehicle_screen.dart`, and `edit_vehicle_screen.dart`.

## [0.3.263] - 2026-09-11

### Fixed (AUT-3225)
- fix(tests): add `sqflite_common_ffi` init to desktop layout tests — resolves `databaseFactory not initialized` error when running `flutter test` on desktop/CI environments.

## [0.3.262] - 2026-09-11

### Fixed (AUT-2683)
- fix(frontend): replace `onReorderItem` with `onReorder` in `edit_build_screen.dart`. `ReorderableListView.builder` does not expose `onReorderItem` in Flutter 3.38.2, causing the amd64 Docker build to fail and blocking the Docker Hub `:latest` multi-arch publish.

## [0.3.261] - 2026-09-10

### Fixed (AUT-3154)
- fix(docs): repair vector-store doc drift — all 5 embedding entity tables (`diagnostics`, `service_records`, `modifications`, `receipts`, `social_issue_posts`) now referenced consistently across `docs/Engineering/ai/vector.md`, `docs/Engineering/database-schema.md`, `docs/Engineering/container-architecture.md`, and `docs/Engineering/architecture.md`. Cross-references that pointed at the non-existent `docs/ai/vector.md` / `docs/README.md` / `postgres-pg17-upgrade.md` now resolve to the canonical `docs/Engineering/ai/vector.md`, `docs/index.md`, and `docs/Deployment-and-Infrastructure/server-migration.md`. Migration comments in `g7h8i9j0k1l2` / `h1i2j3k4l5m6` corrected (pg16 → pg17 image; IVFFlat-claim → HNSW-claim) and `vector.md`'s migration reference table now lists all three vector migrations (`g7h8i9j0k1l2`, `h1i2j3k4l5m6`, `u1v2w3x4y5z6`) with the verified single-head chain (`m3rge06`).

## [0.3.260] - 2026-09-10

### Added (AUT-3162)
- feat(backend): seed deterministic demo fuel stations + prices into demo data for Servo Spy (/fuel/stations, /fuel/stations/{id}/history, /fuel/types, /fuel/brands). Adds 10 Melbourne-area stations across Ampol, BP, Caltex, Woolworths, 11-Seven, Shell, Coles Express with 91/95/98/E10/Diesel/LPG prices, source='demo' + arbitration rows, idempotent per reset_demo cycle.

### Changed (AUT-3153)
- infra(docker): merge the standalone Celery `worker` service into `backend` in `docker-compose.hosted.yml` (Phase 1 pillar a). The backend image already carries the worker dependencies and its default CMD runs API + Celery worker+beat in one container, matching `docker-compose.prod.yml`; the hosted stack drops from 9 to 8 long-running containers. The worker's fuel-poll env (`FUEL_NSW/VIC/QLD/SA_*_FILE`) moved to the backend service. Added `scripts/check-compose-config.py` fuel/dongle secret-file coverage and `scripts/seed-secrets.sh` mappings. Added `docs/Deployment-and-Infrastructure/container-consolidation-migration.md` migration checklist and refreshed the hosted topology/stack tables in `docs/Engineering/container-architecture.md` and `docs/Deployment-and-Infrastructure/deployment-guide.md`.

## [0.3.259] - 2026-09-09

### Fixed (AUT-2656)
- fix(ci): arm64 build-hosted.yml no longer fails with `exec format error` at the first `RUN` step in `docker/backend/Dockerfile`. The previous `python:3.13-slim@sha256:cc9dffa…` pin was a **single-arch amd64** manifest (annotation `com.docker.official-images.bashbrew.arch: amd64`), so the arm64 runner pulled amd64 layers and every `RUN` died with exit 255 — the build never reached flutter/dart2js. Re-pin to the multi-arch index `python:3.13.15-slim-trixie@sha256:9d2e555…` (resolves to aarch64 on arm64) across backend/ai/worker/market-data Dockerfiles and the trivy scan env; add a pin-guard check that the python base index contains an arm64 manifest.

## [0.3.258] - 2026-09-09

### Fixed (AUT-3154)
- fix(docs): repair vector-store doc drift — all 5 embedding entity tables (`diagnostics`, `service_records`, `modifications`, `receipts`, `social_issue_posts`) now referenced consistently across `docs/Engineering/ai/vector.md`, `docs/Engineering/database-schema.md`, `docs/Engineering/container-architecture.md`, and `docs/Engineering/architecture.md`. Cross-references that pointed at the non-existent `docs/ai/vector.md` / `docs/README.md` / `postgres-pg17-upgrade.md` now resolve to the canonical `docs/Engineering/ai/vector.md`, `docs/index.md`, and `docs/Deployment-and-Infrastructure/server-migration.md`. Migration comments in `g7h8i9j0k1l2` / `h1i2j3k4l5m6` corrected (pg16 → pg17 image; IVFFlat-claim → HNSW-claim) and `vector.md`'s migration reference table now lists all three vector migrations (`g7h8i9j0k1l2`, `h1i2j3k4l5m6`, `u1v2w3x4y5z6`) with the verified single-head chain (`m3rge06`).

### Fixed (AUT-3152)
- fix(ai/tests): isolate test env globals. `ai/tests/test_car_check.py`, `test_advisor.py`, `test_fallbacks.py`, `test_parts_guide.py`, `test_router_validation.py`, `test_gateway_security.py`, and `test_social_image.py` previously set `AI_ROUTER_URL` / `AI_GATEWAY_API_KEY` via module-level `os.environ.setdefault`, leaking `AI_GATEWAY_AUTH_DISABLED=1` across the pytest process and producing 2 false 401s in `test_gateway_security.py` during combined runs. All module-level env mutation is now done through per-test `monkeypatch.setenv`/`delenv` autouse fixtures; `test_gateway_security.py` additionally clears `AI_GATEWAY_AUTH_DISABLED` so its 401 assertions hold regardless of run order. Verified: `pytest ai/tests` passes 109/109 both clean (`-u` env) and combined.

## [0.3.260] - 2026-09-10

### Fixed (AUT-2281)
- fix(backend): `cost_per_km` divisor `/100` → `/10000` in `_project_price` (`app/api/v1/fuel_servo.py:399`) so the result is **$/km** not cents/km. The old code pre-divided `price` by 100 then divided again — double conversion. Also fixed `avg_litres_per_fill` → `avg_fill_litres` field-name mismatch in `_station_out` (`app/api/v1/fuel_servo.py:417`) and `annotate_station`/`annotate_prices` (`app/services/fuel_servo.py:69,93`); corrected an `IndentationError` in `_station_out`; updated frozen assertions in `tests/test_aut2201_station_annotations.py`. All 8 tests in `test_aut2201_station_annotations.py` + `test_servo_projection_aut2053.py` pass.

## [0.3.257] - 2026-09-09
### Added (AUT-2352)
- test(frontend): add `frontend/test/app_config_validate_test.dart` — 6 hermetic reachability cases for `AppConfig.validate()` covering 2xx ok, 5xx fail, timeout, connection refused, malformed URL, and `healthz` origin stripping. Per-test isolation via `tearDown` resetting `apiBase` / `lastValidationOk` / `lastValidationError`. Closes AUT-2352.

## [0.3.256] - 2026-09-09

### Security (AUT-2060)
- security(ci,docker): bump python:3.13-slim to digest cc9dffa (libssl3t64 3.5.7-1~deb13u2, resolves CVE-2026-14456 OpenSSL QUIC DoS) and nginx frontend to digest ee1643ae (util-linux/alpine update). Remove resolved CVE-2026-14456 suppression from .trivyignore. Add libuuid/util-linux HIGH CVE suppressions (CVE-2026-53612/53613/53614/76642/78408/78409/78410; nginx frontend never invokes mount/nsenter). Fix trivy-image-scan.yml to use aquasecurity/trivy-action@v0.36.0 with `scanner: vuln` inputs (v0.37.0 does not exist). Drop separate ai service from docker-compose.prod.yml — AI gateway runs inside backend container (AUT-2000). Add libexpat version-check workflow (AUT-2126). Add FUEL_SA_API_KEY/FUEL_SA_ENABLED env vars for SA SAFPIS ingester (AUT-2610).

## [0.3.255] - 2026-09-08

### Fixed (AUT-2656)
- fix(ci): restore arm64 flutter web compile in build-hosted.yml. Pin the
  frontend Dockerfile to `ghcr.io/cirruslabs/flutter:3.38.2` (the `:stable`
  tag had drifted past 3.27.x and introduced breaking Flutter API changes —
  `MaterialBanner.actions` required, `MediaQuery.withClampedTextScaling`
  `maxTextScale` removed, `Connectivity.instance` removed) and re-apply the
  dart2js compat fixes from PR #579 (887c213): `Connectivity()`,
  `Future<Database>? _opening`, indentation in login/signup/add_vehicle/edit_vehicle
  screens, `MaterialBanner.actions` + `MediaQuery` clamp in app.dart.

### Added (AUT-2118)
- backend(tests): add `backend/tests/health_demo.test.py` — dedicated health endpoint CI gate asserting /health returns 200, status=ok, service=autobrain-backend, version matches APP_VERSION, and marks demo/hosted/default env when DEMO_MODE=true. Promoted from test_api.py. Also ships `.github/workflows/ci-tests.yml` (AUT-2119): pytest job on PR + push to main; a failing health_demo.test blocks merge and posts to Discord #updates on failure, keeping hosted/default from drifting out of parity.

## [0.3.254] - 2026-09-08
### Added (AUT-2386)
- feat(backend): source-arbitration rule for multi-feed overlap. ``FuelPrice`` now carries ``source_id`` + ``arbitration_score``; new ``fuel_price_arbitrations`` table stores the daily winning source per (station, fuel_type, day). PR #473.

## [0.3.253] - 2026-09-07
### Fixed (AUT-2656)
- fix(frontend): restore flutter web compile on arm64 runner. PR #530 (AUT-2478) introduced a class name collision in `home_screen.dart` — the `_OwnershipAdvisorLaunchCard` class had its constructor renamed to `_ErrorView`, nesting it and breaking dart2js. Separated `_ErrorView` as its own top-level class and restored `_ErrorView.build` body. Also fixed `servo_spy_screen.dart` `_openHistory()` missing `BuildContext` argument (passed `context` to `Navigator.of(context)` but the method signature lacked the parameter, causing `context` to resolve to the enclosing `build` scope).

## [0.3.252] - 2026-09-07
### Fixed (AUT-2726)
- fix(backend,frontend): apply missing rego columns to existing vehicles + clearer server error messages. `backend/app/db/bootstrap.py` now falls back from `alembic upgrade head` to `alembic upgrade heads` before `create_all`, so a database that predates the `m3rge05` merge migration (which adds `rego_status`, `rego_expiry_date`, `rego_checked_at`, `powertrain`, `rego_state` to `vehicles`) no longer silently skips column creation — `create_all` does not add columns to existing tables, leaving vehicles without rego state and the frontend showing a masked 500 ("Could not reach the server"). `frontend/lib/screens/home/home_screen.dart` now distinguishes `ApiException` (server error, surface the status code + message) from a genuine network timeout so users see the real failure instead of a misleading connection error. Immediate mitigation: missing columns applied directly to hosted, demo, and default databases; `alembic_version` stamped to `m3rge05` on all three.

### Fixed (AUT-2518)
- fix(market-data): relax chrome-sandbox SUID guard to warn-and-continue. Playwright 1234+ (Chrome for Testing) removed `chrome-sandbox` from `/ms-playwright` — Chromium now uses user namespaces in headless mode. The previous `exit 1` on zero matches aborted the `build-hosted.yml` loop before the frontend image could be built. `market-data/Dockerfile` now matches both `chrome-sandbox` (hyphen) and `chrome_sandbox` (underscore) and warns to stderr when neither is present, letting the build continue. The `docker/ai/Dockerfile` already had this behaviour from the AUT-2582 fix. Both images fall back to `--no-sandbox` at runtime per `market-data/browser.py`, so the SUID helper is an optional hardening layer.

## [0.3.251] - 2026-09-07
### Added (AUT-2706)
- firmware+backend: per-row `ev_mode` flag and vehicle-type detection. The ESP32-DIY firmware now computes `ev_mode` per trip row (0=ICE / 1=EV / 2=HYBRID) from RPM-vs-pack_current hysteresis and classifies vehicle type from the dominant ev_mode over the first trip (1=EV, 2=HEV, 4=PHEV), persisting it to the backend via `POST /devices/{device_id}/vehicle-type`. Vehicle type is stored on the `Device` model (`vehicle_type` string column, new Alembic migration `aut2706_device_vehicle_type.py`) with a `DeviceVehicleTypeIn` schema. EV manufacturer PID tables keyed by VIN WMI are selected per AUT-2702, Mode 01 0x2F fuel level is reported for PHEVs, and the firmware self-check (`firmware/esp32-diy/test/self_check.cpp`) now covers the new EV profile and vehicle-type paths. Closes AUT-2706.

## [0.3.250] - 2026-09-07

### Fixed (AUT-2656)
- fix(frontend): replace reverted `withValues(alpha:)` with `withOpacity(alpha:)` in car_check_screen.dart to restore dart2js arm64 build.

## [0.3.249] - 2026-09-07

### Fixed (AUT-2656)
- fix(frontend): remove duplicate `_vehicleId` declarations in servo_spy_screen.dart (2 locations) and add `package:flutter/foundation.dart` import in connectivity_service.dart to resolve dart2js compile errors on arm64 runner. Restores dockerhub-publish + build-hosted arm64 image builds.

## [0.3.248] - 2026-09-07
### Fixed (AUT-2960)
- fix(backend): PDF export table header text was black on dark background (unreadable). Header cells now use a cloned `BodyText` style with `textColor=colors.white` and `fontName=Helvetica-Bold` so the `TEXTCOLOR` table style (which only affects raw strings, not Paragraphs) is no longer relied upon. Applies to both service history and build sheet PDFs.
- feat(backend,AUT-2960): vehicle rego now included in the PDF title on the front page. Service history: `Service History — {label} — {rego}`; build sheet: `Build Sheet — {label} — {rego}`. When rego is empty, title remains clean (no trailing separator). Updated API callers in `services.py` and `mods.py` to pass `vehicle.rego`. Added `test_pdf_export_rego_in_title` test.

### Fixed (AUT-2481)
- frontend(servo-spy): dart2js compile error on `_cartoApiKey`/`_cartoKeyParam`. The two were declared as instance fields on `_ServoSpyScreenState` but referenced from `_ServoSpyMapState.build()` (different class, so name-resolution failed at compile time). Promoted both to file-private top-level `const` so both widget trees see them; removed the `const` from `_cartoKeyParam` (the runtime `isEmpty` check is not a constant expression).

## [0.3.243] - 2026-09-06
### Fixed (AUT-2656)
- fix(frontend): restore flutter web compile on arm64 runner. Three compile errors blocked `flutter build web` in the dockerhub-publish + build-hosted arm64 jobs: (1) `login_screen.dart:199` — `children:` under-indented by 2 spaces; (2) `signup_screen.dart:85` — `child:` under-indented by 2 spaces; (3) `reset_password_web.dart` — `import 'dart:html'` unsupported by Flutter ≥3.22 web builds (CanvasKit renderer), replaced with no-op `clearUrlToken()` (token detection in `app.dart` reads the fragment before navigation, so no data loss).

## [0.3.242] - 2026-09-06

### Added (AUT-2118)
- backend(tests): add `backend/tests/test_health_demo.py` — dedicated health endpoint CI gate asserting /health returns 200, status=ok, service=autobrain-backend, version matches APP_VERSION, and marks demo/hosted/default env when DEMO_MODE=true. Promoted from test_api.py.

## [0.3.241] - 2026-09-06

### Added (AUT-2651)
- backend(advisor): Car Check module (AUT-2651) — deterministic deal score + AI 9Router narrative (system prompt instructs model never to invent numbers). New `POST /api/v1/advisor/car-check` route takes a parsed listing + optional reference price, computes a 0-100 deal score from price/km/age heuristics, then calls 9Router via `run_car_check_ai` (24h in-process LRU+TTL cache, mirrored from `run_advisor_ai`). When 9Router is unreachable, falls back to `car_check_fallback` (rule-based summary with red/green flags). `deal_score` is immutable via `_AI_IMMUTABLE["car-check"]` — the router can enrich prose but never override the score. Schema whitelist `_SCHEMAS["car-check"]` allows only `summary`, `red_flags`, `green_flags`. AI fallback: `ai/app/fallbacks/car_check.py`. AI module: `ai/app/modules/car_check.py`. Backend service: `backend/app/services/car_check.py`. Tests: `ai/tests/test_car_check.py` (17 cases) + `backend/tests/test_car_check_ai.py` (19 cases). Parent: AUT-2630.
### Changed (AUT-1932)
- deploy: VIC Servo Saver fuel feed deployed to Default + Hosted (AUT-1932).

## [0.3.240] - 2026-09-06
### Added (AUT-2703)
- feat(firmware,backend,frontend): extend trip CSV row schema with EV/PHEV fields (`soc_pct,pack_v,pack_a,pack_temp_c,odo_km,ev_mode`) for AUT-2437. `format_trip_row` in `obd_pids.h` now emits 13-field rows (old 7-field rows still accepted via default args). CSV header updated to `epoch,rpm,speed,coolant,throttle,lat,lon,soc_pct,pack_v,pack_a,pack_temp_c,odo_km,ev_mode`. `csv_to_gps_json` (upload_payload.h), backend `parse_board_csv` (trip_gps.py), and frontend `tripCsvToJson` (dongle_relay.dart) all tolerate both old and new row lengths via fixed-position reads. Dart tests expanded with backward-compat + EV-field cases. C++ self_check expanded with EV-field assertions + old-format CSV tolerance.
### Fixed (AUT-2600)
- fix(frontend): restore flutter web compile on arm64 runner. Three compile errors were tripping dart2js: `login_screen.dart:199` (under-indented children), `signup_screen.dart:85` (under-indented child), and `reset_password_web.dart` (dart:html import). Restores dockerhub-publish + build-hosted arm64 image builds.

### Added (AUT-2053)
- feat(fuel/servo): Servo Spy station prices now show `$ per km` and `avg fill cost` projections derived from the requesting user's current vehicle's fuel stats. Backend: `FuelStats` gains `avg_fill_litres` (mean of full-tank fills); `/fuel/stations` and `/fuel/station/{id}/prices` accept `?vehicle_id=` and return `cost_per_km` + `avg_fill_cost` on every `FuelPriceOut`. Silently omits projections when the vehicle is inaccessible or stats are missing. Frontend: `ServoFuelPrice`/`StationRow` rows surface the new fields in both list and map detail views. No AI in the hot path — deterministic arithmetic only. Tests: `backend/tests/test_servo_projection_aut2053.py` + `backend/tests/test_services_extraction.py` extended; frontend tests updated for the new fields. Closes AUT-2053.

### Added (AUT-2449)
- backend(advisor): Ownership Advisor Dream Car module — deterministic lookup + affordability + repayments, no 9Router, no AI. New `POST /api/v1/advisor/dream` route (per ADR 0001) is the third POST module in the Ownership Advisor surface: target lookup anchors on the same cached `market_listing_cache` row the Value module uses (same `(make, model, year)` key shape, 24h TTL — no duplicate storage per ADR §2.5), affordability is pure arithmetic on the optional request body finance profile (`annual_income`, `monthly_expenses`, `cash_on_hand`), and indicative repayments reuse the existing `_loan_monthly_payment` helper the Finance module publishes so consecutive calls return the same numbers for the same inputs. Three blocks in the response: (1) `data.target` — market-data lookup for an arbitrary (make, model, year), with low/mid/high band, source, sample_size, and a `note` explaining the gap when the cache has no row; (2) `data.affordability` — `deposit_required`, `monthly_disposable_income`, `cash_gap` (negative = shortfall), and a `surplus` flag that fires only when the user can fund the deposit AND keep the indicative monthly under the 30% debt-service-ratio ceiling on disposable income; (3) `data.repayments` — `principal`, `monthly_repayment`, `total_interest` with the same constants the Finance module publishes (term clamped to [12, 84] default 60, rate clamped to [0, 30] default 7.5% p.a., deposit clamped to [0, 100] default 20%). Finance inputs are ephemeral — no DB migration, no user-settings tab (ADR §2.4); when `annual_income`/`monthly_expenses` are missing the affordability block returns a well-formed `note` explaining the gap instead of crashing. `vehicle_id` in the envelope is `None` (Dream Car is not anchored on the user's current vehicle). Free accounts get 403. New schemas: `AdvisorDreamRequest`, `DreamTarget`, `DreamAffordability`, `DreamRepayments`, `AdvisorDreamData` (`backend/app/schemas/advisor.py`). New service helper `compute_dream` plus constant clamps (`DREAM_DSR_CEILING`, `DREAM_DEFAULT_FINANCE_TERM_MONTHS`, etc.) in `backend/app/services/advisor.py`. New route `POST /api/v1/advisor/dream` in `backend/app/api/v1/advisor.py` (registered alongside the Value/Finance/AI routes); entitlement gate reuses `_enforce_entitlement` (free accounts get 403). Tests: `backend/tests/test_advisor_dream.py` covers three regions: target-lookup shape (market_data cache miss/hit, note propagation), affordability arithmetic (no profile → note, surplus/shortfall flags under 30% DSR ceiling), and repayments math (principal = mid × (1 - deposit_pct), monthly = `_loan_monthly_payment`, edge cases for zero rate / clamped term). Closes AUT-2449.

### Fixed (AUT-2618)
- fix(ci): replace 42 occurrences of `Color.withValues(alpha:)` (requires Flutter ≥3.27) with `Color.withOpacity(alpha:)` (deprecated but supported across 3.x) in 16 frontend files. The `ghcr.io/cirruslabs/flutter:stable` Docker image auto-upgraded to a Flutter version that doesn't support `withValues`, causing `dart2js` to fail with `Error: Can't find ')' to match '('` at every `withValues(alpha:)` call site during `flutter build web`. This blocked `build-hosted.yml` (amd64 + arm64) since 10:37Z and prevented any new hosted images (including AUT-2446 Replace + AUT-2447 Upgrade) from reaching EP5. `dart:html` warning in `reset_password_web.dart` is unrelated (wasm dry-run, not fatal).

### Added (AUT-2447)
- backend(advisor): Ownership Advisor Upgrade module — deterministic upgrade options + similar suggestions + trade-up estimate. New `GET /api/v1/advisor/upgrade` route anchors on the value module's cached market median. No 9Router. No AI. Free accounts get 403. New schemas `UpgradeOption`, `SimilarVehicleSuggestion`, `TradeUpDelta`, `AdvisorUpgradeData`. New helpers `compute_upgrade`, `find_upgrade_options`, `find_similar_vehicles`, `build_trade_up`, `_amortize_monthly`, `_similarity_score`, `_clamp_finance_term/rate/deposit_pct`, `_tier_label`, `_median_for`. Tests: `backend/tests/test_advisor_upgrade.py`.

### Added (AUT-2478)
- feat(frontend,advisor): Ownership Advisor launch card on `HomeScreen` — a full-width purple (`#6366F1`) branded card above the feature grid with title, tagline, and a `Wrap` of six `_ModuleChip` pills (Value/Replace/Upgrade/Finance/Dream/AI) mirroring the 6-module Overview shell per AUT-2451. The existing feature-tile entry is preserved so users who scroll past the launch card still reach `AdvisorOverviewScreen(vehicleId:)` via `_AdvisorEntry`. Copy matches the `#changelog` embed payload for sibling AUT-2477 (module names, "deterministic where possible, AI only for the final call"). New test `test/advisor_home_card_test.dart` (4 cases: card found, title, tagline, chip count). Closes AUT-2478.

### Added (AUT-2376)
- feat(frontend): Servo Spy station detail — 30-day price history chart. Tapping
  a station in the Servo Spy **list** view (or the **map** detail sheet) opens
  a new screen that calls `GET /api/v1/fuel/stations/{id}/history` and renders
  one `fl_chart` `LineChart` line per fuel type (E10, 91, 95, 98, Diesel, LPG)
  for the last 30 days, with a legend, a `\$x.xx` Y axis, and tap-to-tooltip.
  The client groups the flat `(fuel_type, price, effective_at)` response from
  the AUT-2375 endpoint by fuel type. Cached in-memory per station so a
  re-open is instant. Empty state ("No price history yet") and 404 fallback
  handled. New unit tests `frontend/test/fuel_prices_api_test.dart` cover the
  flat contract and empty/404 cases. Closes AUT-2376.

### Added (AUT-2416)
- mobile+web: premium-only **Rego Lookup** tool. New `frontend/lib/screens/rego/rego_lookup_screen.dart` lets premium users type an Australian plate + state, hits the existing `POST /vehicles/rego-lookup` endpoint, and renders VIN + vehicle details + rego status + expiry in a card. Plate input is uppercase / alphanumeric / 8-char max via `TextInputFormatter`. Premium gate via `AuthState.premium`; non-premium sees the `PremiumGate` upgrade prompt (screen never calls the endpoint). New `Rego Lookup` feature tile on the home grid, only inserted for premium users so the entry doesn't appear at all on free plans. Backend result now persists `rego_status` / `rego_expiry_date` / `rego_checked_at` on the Vehicle (new model columns + Alembic migration `a1b2c3d4e5f8`) so the badge + expiry notification both read the cache. Status mapping (`valid`/`registered`/`current`/`active` → `registered`; `expired`/`unregistered`/`cancelled` → `expired`) lives in `app.services.rego._map_provider`. `VehicleOut` schema exposes the new fields (always ISO `YYYY-MM-DD`).
- mobile+web: premium-only **Rego expiry alert** setting. New `notification_preferences.rego_expiry_days` column (0 = off). The settings card on `NotificationsScreen` adds a "Rego expiry alert" section with a "PREMIUM" chip and a number input; non-premium sees the `PremiumGate` lock instead of the field. The existing `run_daily_notification_checks` Celery beat task now evaluates rego expiry for every premium user: when `vehicle.rego_expiry_date - today <= pref.rego_expiry_days` (and no dedupe row exists) it fires `deliver_rego_expiry` on the user's existing channels (email / Discord / push). Reuses the same delivery + dedupe pattern as `service_due_days`. New `rego_expiry` kind in `NotificationDelivery` and the dedupe `IN` list. `NotificationPreferenceIn` / `NotificationPreferenceOut` schemas accept the field. Migration `a1b2c3d4e5f8` adds both the preference and vehicle columns atomically; merges the AUT-1859 fuel-price-alerts branch so `alembic upgrade head` stays a single linear path (AUT-702 single-head guard). Tests: `backend/tests/test_rego_expiry_notify_aut2416.py` (10 cases) + `frontend/test/rego_lookup_screen_test.dart` (7 cases).
- mobile+web: rego status badge + expiry on every vehicle card. New `Vehicle.regoStatus` / `Vehicle.regoExpiryDate` fields (parsed from `rego_status` / `rego_expiry_date`) drive a green/red `RegoStatusBadge` widget shown on the home hero card and the vehicle-list rows. Forward-compatible with AUT-2414's nightly Celery beat job: when `rego_status` / `rego_expiry_date` are absent the badge is hidden entirely. Gated behind `AuthState.premium` so free accounts see no rego chrome. `formattedRegoExpiry` renders `12 Mar 2027` style dates. Tests: `frontend/test/rego_status_badge_test.dart`.

### Added (AUT-2451)
- feat(frontend,advisor): Ownership Advisor front-door — single home-screen card on `HomeScreen` that opens a 7-tab nested shell (Overview + 6 sub-modules) per ADR 0001. Overview tab shows 6 `ActionChip` chips routing Value/Replace/Upgrade/Finance/Dream/AI into their own screens. Back button preserves tab selection when navigating back to the Advisor. Deep-links `/advisor/{value|replace|upgrade|finance|dream|ai}` select the matching tab from the home screen; unknown tokens fall through to Overview. Offline path: `AdvisorApi._callWithCache` reads `OfflineCache` before every request and serves the cached response on any `ApiException`, so each sub-module shows a cached last-known snapshot when offline. New files: `lib/screens/advisor/advisor_models.dart` (shared `AdvisorResponse`/`AdvisorValueData`/`AdvisorFinanceData`/etc.), `lib/screens/advisor/advisor_api.dart` (`AdvisorApi` + `cacheKey` + `_bodyKey`), and one screen per module (`value_screen.dart`, `replace_screen.dart`, `upgrade_screen.dart`, `finance_screen.dart`, `dream_screen.dart`, `ai_screen.dart`). Test: `test/advisor_overview_test.dart` (3 widget tests: seven-tab shell, initial-tab selection, chip count). Mobile team will split these same files into `autobrain-mobile` unchanged.

### Fixed (AUT-1878)
- fix(deploy): pin hosted worker to a specific arm64 digest in `docker-compose.hosted.yml` and replace the Celerybeat-schedule mtime HEALTHCHECK with a deterministic `/proc` PID + `GET /health` probe. The previous mtime probe falsely flapped when no tasks were due within the window (the production norm for the worker), cycling containers; the new probe stays Healthy on the Oracle VM.

### Added (AUT-2446)
- backend(advisor): Ownership Advisor Replace module — deterministic used/new replacement cost + funding gap + monthly saving target. New `GET /api/v1/advisor/replace` route (per ADR 0001) anchors on the same cached `market_listing_cache` median the Value module uses — no 9Router, no AI. Used replacement cost = current private-sale mid; new replacement cost applies age-based new-vs-used premium curve (1.0× at 0y → 1.4× at 3y → 1.8× at 6y → 2.2× at 10y, clamped at 3.0×). Funding gap: `gap = replacement_cost - current_value - trade_in_mid`; `monthly_target = gap / horizon_months`. Negative gap = `surplus=true` with zero monthly. Free accounts get 403. New schemas `AdvisorReplaceData`, `FundingGapBand`. New helpers `compute_replace`, `age_years`, `new_used_premium`, `_clamp_horizon`. Tests: `backend/tests/test_advisor_replace.py`.

### Added (AUT-2376)
- feat(frontend): Servo Spy station detail — 30-day price history chart. Tapping
  a station in the Servo Spy **list** view (or the **map** detail sheet) opens
  a new screen that calls `GET /api/v1/fuel/stations/{id}/history` and renders
  one `fl_chart` `LineChart` line per fuel type (E10, 91, 95, 98, Diesel, LPG)
  for the last 30 days, with a legend, a `\$x.xx` Y axis, and tap-to-tooltip.
  The client groups the flat `(fuel_type, price, effective_at)` response from
  the AUT-2375 endpoint by fuel type. Cached in-memory per station so a
  re-open is instant. Empty state ("No price history yet") and 404 fallback
  handled. New unit tests `frontend/test/fuel_prices_api_test.dart` cover the
  flat contract and empty/404 cases. Closes AUT-2376.

## [0.3.239] - 2026-09-05

### Added (AUT-2450)
- backend+ai(advisor): AI Advisor module. New `POST /api/v1/advisor/ai` route consumes structured outputs from the Value/Replace/Upgrade/Finance/Dream sub-modules and returns `{decision, confidence, rationale, next_actions, based_on}`. Deterministic-first per ADR 0001: a small rule tree (mirrored in `backend/app/services/advisor.compute_advisor_recommendation` and `ai/app/fallbacks/advisor.advisor_fallback`) always runs and its decision is the source of truth; 9Router may add a richer rationale and sharper `next_actions` but cannot change the decision (listed in `_AI_IMMUTABLE["advisor"]` and the system prompt forbids it). The AI never invents numbers — any number in the response is one of the supplied module outputs verbatim. Graceful fallback: when the AI gateway is unreachable the route returns the deterministic baseline with `model = "rule-based-fallback"` and `factors.fallback_reason = "ai_gateway_unreachable"`; the user always gets an answer. 24h in-process LRU+TTL cache keyed by `sha256(sorted_module_outputs)` in `app.services.ai_client` (per the spec; per-process is acceptable because the cache only optimises repeat calls, not correctness — restart-eviction loses nothing). New `AdvisorAIRequest` + `AdvisorAIData` + `AdvisorAIBasedOn` schemas in `backend/app/schemas/advisor.py`; new `app.services.ai_client.run_advisor_ai`; new AI-gateway module `ai/app/modules/advisor.py` + system prompt + `_SCHEMAS["advisor"]` + `_AI_IMMUTABLE["advisor"]` in `ai/app/router_utils.py`. New module is registered in `ai/app/modules/__init__.py: MODULES["advisor"]` and the route is registered in `backend/app/api/v1/advisor.py`. Free accounts get 403 (same as every advisor module). Tests: `backend/tests/test_advisor_ai.py` (14 cases: pure-helper decision tree, never-invents-numbers invariant, request/response schema, FastAPI route for both gateway-up and gateway-down, free-account 403, cache dedupe); `ai/tests/test_advisor.py` (19 cases: gateway fallback, validate_advisor_response clamp, module registration, system-prompt/immutable/schema contract).

### Changed (AUT-2619)
- chore(mobile-release): gate the APK build in `autobrain-mobile`'s `release-mobile.yml` on a 2-day cooldown + a meaningful-change check so store binaries are only produced when mobile code (`lib/`, `assets/`) changed since the previous release and at least 48h have passed since the last APK build (floating `apk-built` tag ref). Pure version bumps skip the APK; the `.aab` is never throttled. `docs/mobile-release.md` + `docs/ci-cd.md` updated to document the policy.

### Added (AUT-2450)
- backend+ai(advisor): AI Advisor module. New `POST /api/v1/advisor/ai` route consumes structured outputs from the Value/Replace/Upgrade/Finance/Dream sub-modules and returns `{decision, confidence, rationale, next_actions, based_on}`. Deterministic-first per ADR 0001: a small rule tree (mirrored in `backend/app/services/advisor.compute_advisor_recommendation` and `ai/app/fallbacks/advisor.advisor_fallback`) always runs and its decision is the source of truth; 9Router may add a richer rationale and sharper `next_actions` but cannot change the decision (listed in `_AI_IMMUTABLE["advisor"]` and the system prompt forbids it). The AI never invents numbers — any number in the response is one of the supplied module outputs verbatim. Graceful fallback: when the AI gateway is unreachable the route returns the deterministic baseline with `model = "rule-based-fallback"` and `factors.fallback_reason = "ai_gateway_unreachable"`; the user always gets an answer. 24h in-process LRU+TTL cache keyed by `sha256(sorted_module_outputs)` in `app.services.ai_client` (per the spec; per-process is acceptable because the cache only optimises repeat calls, not correctness — restart-eviction loses nothing). New `AdvisorAIRequest` + `AdvisorAIData` + `AdvisorAIBasedOn` schemas in `backend/app/schemas/advisor.py`; new `app.services.ai_client.run_advisor_ai`; new AI-gateway module `ai/app/modules/advisor.py` + system prompt + `_SCHEMAS["advisor"]` + `_AI_IMMUTABLE["advisor"]` in `ai/app/router_utils.py`. New module is registered in `ai/app/modules/__init__.py: MODULES["advisor"]` and the route is registered in `backend/app/api/v1/advisor.py`. Free accounts get 403 (same as every advisor module). Tests: `backend/tests/test_advisor_ai.py` (14 cases: pure-helper decision tree, never-invents-numbers invariant, request/response schema, FastAPI route for both gateway-up and gateway-down, free-account 403, cache dedupe); `ai/tests/test_advisor.py` (19 cases: gateway fallback, validate_advisor_response clamp, module registration, system-prompt/immutable/schema contract).

### Added (AUT-2543)
- docs: `docs/home-assistant-integration.md` — Home Assistant setup guide: token
  creation (`POST /api/v1/ha/tokens`), `rest` + `command_line` sensor examples for
  `/api/v1/ha/vehicles`, `/service-reminders`, per-vehicle `/analytics` and
  `/service-intervals`, service-due mobile-notification automation (≤7d), Lovelace
  cards, and the optional `wss://<host>/ws/ha/{vehicle_id}` real-time push path.
  Registered the HA route table (`GET /ha/vehicles`, `/vehicles/{id}/service-intervals`,
  `/vehicles/{id}/analytics`, `/service-reminders`; `POST/GET/DELETE /ha/tokens`)
  in `docs/api-spec.md`.

### Added (AUT-2543)
- tests: `backend/tests/test_ha_docs.py` — drift guard asserting the documented
  `/api/v1/ha/*` paths match the real router table (catches the `ha/v1/` double-
  prefix regression from the draft PR) and that every field referenced in the doc
  examples exists on the `HaAnalyticsOut`/`HaServiceReminderOut`/`HaServiceIntervalOut`
  /`HaVehicleOut` schemas. Skips the field-name checks while AUT-2541's schemas
  are absent so CI stays green on `main`; activates once PR-520 lands.

## [0.3.238] - 2026-09-05

### Fixed (AUT-2526)
- fix(frontend, web): cap content width on the desktop web app so screens reported as oversized in the audit no longer stretch to 1920px. Added `frontend/lib/widgets/responsive.dart` with a `CenteredMaxWidth` layout widget, `Breakpoints` (desktop ≥1100, wideDesktop 1400) and a `BuildContext.isDesktop` extension. Wrapped the bodies of: home dashboard, Servo Spy map controls + error banner, vehicle list, vehicle timeline, settings, login, signup, server setup, forgot-password, reset-password, add-vehicle, edit-vehicle and share-vehicle. Home `FeatureGrid` now picks `crossAxisCount` 2/3/4 by width (mobile / desktop / wide desktop) and the `childAspectRatio` widens on desktop. Added a global `MediaQuery.withClampedTextScaling(maxScale: 1.5)` in `app.dart` `builder` so desktop zoom can't balloon text beyond a readable ceiling. Added `frontend/test/responsive_test.dart` covering the breakpoint constants and the `CenteredMaxWidth` cap on 1920px.

## [0.3.237] - 2026-09-05

### Fixed (AUT-2108)
- fix(backend): `Settings` now declares `AI_ROUTER_API_KEY_FILE` and a `model_validator` populates `AI_ROUTER_API_KEY` from the secret file when the plain env var is unset. Compose already set `AI_ROUTER_API_KEY_FILE=/run/secrets/ai_router_api_key` (AUT-1533), but the field did not exist on `Settings`, so the file was never read and embedding requests to the 9Router went unauthenticated. Plain env still wins; missing files are silently skipped. Parent: AUT-2091.

## [0.3.236] - 2026-09-05
### Fixed (AUT-2568)
- fix(deploy): frontend healthcheck in `docker-compose.yml`, `docker-compose.prod.yml`, and `docker-compose.hosted.yml` now references `${BACKEND_URL:-http://backend:8000}` (matching the existing `environment:` block) instead of bare `${BACKEND_URL}`, so compose interpolation can never resolve the URL to empty at deploy time (AUT-2350 follow-up: was producing `wget: bad address "/health"` and flipping the Portainer frontend container unhealthy). Also fixes the grep pattern from `"status": "ok"` to `"status":"ok"` so it matches FastAPI/ORJSON compact output `{"status":"ok",...}` — the with-space variant never matched and would silently re-break the healthcheck on a fresh redeploy from main. Repo now matches the stack actually running on EP5 (frontend Healthy).

## [0.3.235] - 2026-09-04
### Fixed (AUT-2467)
- fix(backend): resolve structlog `source` kwarg collision in `ingest_fuel_prices` (`app/workers/tasks.py:509`). `res` dict from `ingest_all_fuel` already contains a `source` key; passing `source=source` as a separate kwarg caused `TypeError: got multiple values for keyword argument 'source'`. Now logged as `logger.info("fuel_ingest_summary", **res)`. Also fixed `_run(_run())` in `run_due_checks` (`app/services/notify.py:257`) — inner `_run` had no args, so the coroutine was never scheduled. Renamed to `_coro` and routed through `tasks._run()`. Adds regression tests `test_ingest_fuel_prices_no_typeerror_when_source_in_result` and `test_run_due_checks_calls_check_for_each_vehicle`.

## [0.3.234] - 2026-09-04

### Fixed (AUT-2484)
- redeploy(homed): bump autobrain-backend :hosted-arm64 digest to include AUT-2277 duplicate-FuelPrice-class fix. EP5 was crash-looping on the pre-fix image (two `FuelPrice` classes claiming `fuel_prices` in `Base.metadata`). Source fix is already merged (f7db5b6d); rebuilt arm64 image from main `6e394007` and pinned the new digest in `docker-compose.hosted.yml`.

### Fixed (AUT-2469)
- fix(hosted, ci): replace standalone `myoung34/github-runner:latest` (amd64-only) on EP5 with a compose-managed `gh-runner` service using the official multi-arch `ghcr.io/actions/actions-runner:latest` (includes linux/arm64 binaries). The myoung34 image shipped amd64-only `.NET` binaries (`Runner.Listener`, `libcoreclr.so`); on the aarch64 Oracle VM the runner was in a permanent restart loop (`ldd: ./bin/libcoreclr.so: No such file or directory`), leaving ARM CI on Hosted dead. `build-hosted.yml` arm64 builds are unblocked. `docker/runner/entrypoint.sh` refreshes the short-lived runner registration token on every boot via the PAT secret file (AUT-1533 `*_FILE` pattern). `docker-compose.hosted.yml` now defines the `gh-runner` service; `scripts/seed-secrets.sh` seeds `github_pat` into the secrets dir. Deployment: stop the old standalone container before `docker compose up` to avoid a name collision (`docker stop gh-runner-autobrain-arm64 && docker rm gh-runner-autobrain-arm64`).

## [0.3.238] - 2026-09-05

### Fixed (AUT-2526)
- fix(frontend, web): cap content width on the desktop web app so screens reported as oversized in the audit no longer stretch to 1920px. Added `frontend/lib/widgets/responsive.dart` with a `CenteredMaxWidth` layout widget, `Breakpoints` (desktop ≥1100, wideDesktop 1400) and a `BuildContext.isDesktop` extension. Wrapped the bodies of: home dashboard, Servo Spy map controls + error banner, vehicle list, vehicle timeline, settings, login, signup, server setup, forgot-password, reset-password, add-vehicle, edit-vehicle and share-vehicle. Home `FeatureGrid` now picks `crossAxisCount` 2/3/4 by width (mobile / desktop / wide desktop) and the `childAspectRatio` widens on desktop. Added a global `MediaQuery.withClampedTextScaling(maxScale: 1.5)` in `app.dart` `builder` so desktop zoom can't balloon text beyond a readable ceiling. Added `frontend/test/responsive_test.dart` covering the breakpoint constants and the `CenteredMaxWidth` cap on 1920px.

## [0.3.237] - 2026-09-05

### Fixed (AUT-2108)
- fix(backend): `Settings` now declares `AI_ROUTER_API_KEY_FILE` and a `model_validator` populates `AI_ROUTER_API_KEY` from the secret file when the plain env var is unset. Compose already set `AI_ROUTER_API_KEY_FILE=/run/secrets/ai_router_api_key` (AUT-1533), but the field did not exist on `Settings`, so the file was never read and embedding requests to the 9Router went unauthenticated. Plain env still wins; missing files are silently skipped. Parent: AUT-2091.

## [0.3.236] - 2026-09-05
### Fixed (AUT-2568)
- fix(deploy): frontend healthcheck in `docker-compose.yml`, `docker-compose.prod.yml`, and `docker-compose.hosted.yml` now references `${BACKEND_URL:-http://backend:8000}` (matching the existing `environment:` block) instead of bare `${BACKEND_URL}`, so compose interpolation can never resolve the URL to empty at deploy time (AUT-2350 follow-up: was producing `wget: bad address "/health"` and flipping the Portainer frontend container unhealthy). Also fixes the grep pattern from `"status": "ok"` to `"status":"ok"` so it matches FastAPI/ORJSON compact output `{"status":"ok",...}` — the with-space variant never matched and would silently re-break the healthcheck on a fresh redeploy from main. Repo now matches the stack actually running on EP5 (frontend Healthy).

## [0.3.235] - 2026-09-04
### Fixed (AUT-2467)
- fix(backend): resolve structlog `source` kwarg collision in `ingest_fuel_prices` (`app/workers/tasks.py:509`). `res` dict from `ingest_all_fuel` already contains a `source` key; passing `source=source` as a separate kwarg caused `TypeError: got multiple values for keyword argument 'source'`. Now logged as `logger.info("fuel_ingest_summary", **res)`. Also fixed `_run(_run())` in `run_due_checks` (`app/services/notify.py:257`) — inner `_run` had no args, so the coroutine was never scheduled. Renamed to `_coro` and routed through `tasks._run()`. Adds regression tests `test_ingest_fuel_prices_no_typeerror_when_source_in_result` and `test_run_due_checks_calls_check_for_each_vehicle`.

## [0.3.234] - 2026-09-04

### Fixed (AUT-2484)
- redeploy(homed): bump autobrain-backend :hosted-arm64 digest to include AUT-2277 duplicate-FuelPrice-class fix. EP5 was crash-looping on the pre-fix image (two `FuelPrice` classes claiming `fuel_prices` in `Base.metadata`). Source fix is already merged (f7db5b6d); rebuilt arm64 image from main `6e394007` and pinned the new digest in `docker-compose.hosted.yml`.

### Fixed (AUT-2469)
- fix(hosted, ci): replace standalone `myoung34/github-runner:latest` (amd64-only) on EP5 with a compose-managed `gh-runner` service using the official multi-arch `ghcr.io/actions/actions-runner:latest` (includes linux/arm64 binaries). The myoung34 image shipped amd64-only `.NET` binaries (`Runner.Listener`, `libcoreclr.so`); on the aarch64 Oracle VM the runner was in a permanent restart loop (`ldd: ./bin/libcoreclr.so: No such file or directory`), leaving ARM CI on Hosted dead. `build-hosted.yml` arm64 builds are unblocked. `docker/runner/entrypoint.sh` refreshes the short-lived runner registration token on every boot via the PAT secret file (AUT-1533 `*_FILE` pattern). `docker-compose.hosted.yml` now defines the `gh-runner` service; `scripts/seed-secrets.sh` seeds `github_pat` into the secrets dir. Deployment: stop the old standalone container before `docker compose up` to avoid a name collision (`docker stop gh-runner-autobrain-arm64 && docker rm gh-runner-autobrain-arm64`).

## [0.3.238] - 2026-09-05

### Fixed (AUT-2526)
- fix(frontend, web): cap content width on the desktop web app so screens reported as oversized in the audit no longer stretch to 1920px. Added `frontend/lib/widgets/responsive.dart` with a `CenteredMaxWidth` layout widget, `Breakpoints` (desktop ≥1100, wideDesktop 1400) and a `BuildContext.isDesktop` extension. Wrapped the bodies of: home dashboard, Servo Spy map controls + error banner, vehicle list, vehicle timeline, settings, login, signup, server setup, forgot-password, reset-password, add-vehicle, edit-vehicle and share-vehicle. Home `FeatureGrid` now picks `crossAxisCount` 2/3/4 by width (mobile / desktop / wide desktop) and the `childAspectRatio` widens on desktop. Added a global `MediaQuery.withClampedTextScaling(maxScale: 1.5)` in `app.dart` `builder` so desktop zoom can't balloon text beyond a readable ceiling. Added `frontend/test/responsive_test.dart` covering the breakpoint constants and the `CenteredMaxWidth` cap on 1920px.

## [0.3.237] - 2026-09-05

### Fixed (AUT-2108)
- fix(backend): `Settings` now declares `AI_ROUTER_API_KEY_FILE` and a `model_validator` populates `AI_ROUTER_API_KEY` from the secret file when the plain env var is unset. Compose already set `AI_ROUTER_API_KEY_FILE=/run/secrets/ai_router_api_key` (AUT-1533), but the field did not exist on `Settings`, so the file was never read and embedding requests to the 9Router went unauthenticated. Plain env still wins; missing files are silently skipped. Parent: AUT-2091.

## [0.3.236] - 2026-09-05
### Fixed (AUT-2568)
- fix(deploy): frontend healthcheck in `docker-compose.yml`, `docker-compose.prod.yml`, and `docker-compose.hosted.yml` now references `${BACKEND_URL:-http://backend:8000}` (matching the existing `environment:` block) instead of bare `${BACKEND_URL}`, so compose interpolation can never resolve the URL to empty at deploy time (AUT-2350 follow-up: was producing `wget: bad address "/health"` and flipping the Portainer frontend container unhealthy). Also fixes the grep pattern from `"status": "ok"` to `"status":"ok"` so it matches FastAPI/ORJSON compact output `{"status":"ok",...}` — the with-space variant never matched and would silently re-break the healthcheck on a fresh redeploy from main. Repo now matches the stack actually running on EP5 (frontend Healthy).

## [0.3.235] - 2026-09-04
### Fixed (AUT-2467)
- fix(backend): resolve structlog `source` kwarg collision in `ingest_fuel_prices` (`app/workers/tasks.py:509`). `res` dict from `ingest_all_fuel` already contains a `source` key; passing `source=source` as a separate kwarg caused `TypeError: got multiple values for keyword argument 'source'`. Now logged as `logger.info("fuel_ingest_summary", **res)`. Also fixed `_run(_run())` in `run_due_checks` (`app/services/notify.py:257`) — inner `_run` had no args, so the coroutine was never scheduled. Renamed to `_coro` and routed through `tasks._run()`. Adds regression tests `test_ingest_fuel_prices_no_typeerror_when_source_in_result` and `test_run_due_checks_calls_check_for_each_vehicle`.

### Fixed (AUT-2383)
- fix(frontend,servo-spy): CARTO basemap tile URL query param was `?api_key=` but CARTO requires `?key=` — the watermark persisted because the API silently ignored the wrong parameter. Updated tile URL template in `frontend/lib/screens/servo_spy/servo_spy_screen.dart` to use `?key=$_cartoApiKey`; updated comment in `docker/frontend/Dockerfile`. Caching is already optimal: tiles are immutable `{z}/{x}/{y}` hashes so CDN/browser cache-hit rate is naturally high — no extra layer needed.

### Fixed (AUT-2383)
- fix(frontend): CARTO basemap tile URL now uses `?key=` instead of `?api_key=`. The legacy `?api_key=` parameter is silently ignored by CARTO raster basemaps, leaving the "API key required" watermark on Servo Spy's map even with `CARTO_API_KEY` injected. `?key=` is CARTO's required parameter name; `flutter_map`'s `BuiltInMapCachingProvider` handles disk tile caching to keep request volume low. Regression test in `frontend/test/servo_spy_carto_key_test.dart`.

## [0.3.234] - 2026-09-04

### Fixed (AUT-2484)
- redeploy(homed): bump autobrain-backend :hosted-arm64 digest to include AUT-2277 duplicate-FuelPrice-class fix. EP5 was crash-looping on the pre-fix image (two `FuelPrice` classes claiming `fuel_prices` in `Base.metadata`). Source fix is already merged (f7db5b6d); rebuilt arm64 image from main `6e394007` and pinned the new digest in `docker-compose.hosted.yml`.

### Fixed (AUT-2469)
- fix(hosted, ci): replace standalone `myoung34/github-runner:latest` (amd64-only) on EP5 with a compose-managed `gh-runner` service using the official multi-arch `ghcr.io/actions/actions-runner:latest` (includes linux/arm64 binaries). The myoung34 image shipped amd64-only `.NET` binaries (`Runner.Listener`, `libcoreclr.so`); on the aarch64 Oracle VM the runner was in a permanent restart loop (`ldd: ./bin/libcoreclr.so: No such file or directory`), leaving ARM CI on Hosted dead. `build-hosted.yml` arm64 builds are unblocked. `docker/runner/entrypoint.sh` refreshes the short-lived runner registration token on every boot via the PAT secret file (AUT-1533 `*_FILE` pattern). `docker-compose.hosted.yml` now defines the `gh-runner` service; `scripts/seed-secrets.sh` seeds `github_pat` into the secrets dir. Deployment: stop the old standalone container before `docker compose up` to avoid a name collision (`docker stop gh-runner-autobrain-arm64 && docker rm gh-runner-autobrain-arm64`).

## [0.3.232] - 2026-09-04
### Fixed (AUT-2472)
- docker(ai): Playwright 1.62+ removed `chrome-sandbox` under `/ms-playwright` (kernel-namespace sandbox replaces SUID). The AUT-1739 `RUN find ... -name chrome-sandbox | chown root:root && chmod 4755` was failing every hosted build with `FATAL: no chrome-sandbox found`. Relaxed the guard: if at least one `chrome-sandbox` is found, re-SUID it; if none, log a warning and continue (the market-data scraper already falls back to `--no-sandbox` per `market-data/browser.py:81,158`). Keeps the build green and the AUT-2258 hard-fail behaviour when `chrome-sandbox` exists but is mis-owned.

### Added
- feat(fuel): AUT-2381 multi-source data-quality arbitration (best-price selection per station, SourceTrust enum)
### Fixed (AUT-2402 B1)
- fix(backend): `enable_utc=False` on the Celery app. AUT-2375 set `timezone="Australia/Sydney"` but left `enable_utc=True`, which forces Celery to interpret crontab schedules in UTC regardless of the `timezone` value — so `crontab(hour=2)` was firing at 02:00 UTC = 13:00 AEST, not the intended 02:00 AEST off-peak window. With `enable_utc=False`, the cron resolves in `Australia/Sydney` and the daily ingest lands at the intended wall-clock time. Test `test_celery_app_beat_uses_sydney_timezone_for_off_peak_cron` now asserts both `timezone == "Australia/Sydney"` and `enable_utc is False`.

### Fixed (AUT-2404)
- fix(backend): drop legacy `ingest-fuel-prices` beat entry from `app/workers/celery_app.py`. AUT-2375 added `fuel-ingest-all-daily` on the same 02:00 cron, so both fired daily and each upstream fuel feed (WA FuelWatch, NSW FuelCheck, QLD Fuel Prices) was hit twice per day for identical rows. Backwards-compat alias `ingest_fuel_prices = ingest_fuel_all` in `tasks.py` is preserved for dashboard / ad-hoc `.delay()` callers.

### Fixed (AUT-2403 rebase follow-ups)
- fix(backend): `app/services/fuel_prices.py` `from __future__ import annotations` moved to line 1 (was buried after the module docstring, line 188) so test_api / test_fuel_price_alerts can collect the module under Python 3.13. Pre-existing since PR #347 (AUT-1868) — surfaced by the AUT-2403 rebase because the smoke collection now hits the import path.
- fix(backend): add `FuelPriceWatchlistIn` / `FuelPriceWatchlistOut` pydantic schemas (`direction ∈ {up,down,both}`, `threshold_pct > 0`, defaults `both` / `5.0`). `backend/app/api/v1/fuel_prices.py` imports them since PR #347 but the schema definitions were never added, so 30+ test modules fail pytest collection (`cannot import name 'FuelPriceWatchlistIn'`).
- feat(backend): add `compute_price_change(price, previous)` pure helper to `app/services/fuel_prices.py` — day-over-day % move + up/down direction (AUT-1859). Returns `(None, None)` until both prices are present and previous is non-zero; zero delta is `(0.0, None)`. Used by `app/workers/tasks.py::check_fuel_price_alerts` (already importing it) and the watchlist unit tests.
- fix(backend): alembic migration `aut2375_fuel_history_index` `down_revision` rebased from `z2a3b4c5d6e7` to `aut2434_vehicle_powertrain` so the migration chain has a single head after AUT-2434 (vehicle powertrain) landed on main (originally `aut1859_fuel_price_alerts`, then `aut2434_vehicle_powertrain` once that migration reached main).

### Added (AUT-2375)
- feat(backend): Servo Spy fuel ingest now runs **once per day at 02:00 AEST** via Celery beat (`fuel-ingest-all-daily` cron, `timezone="Australia/Sydney"`, `enable_utc=False` so crontab schedules resolve in `Australia/Sydney` rather than UTC — see AUT-2402 B1). The previous 6-hour interval was over-fetching every upstream fuel API — every client request still served cached rows, but the schedule itself made a fresh API call four times a day for no UX gain. New schedule entries:
    - `fuel-ingest-all-daily` (`ingest_fuel_all`) — single source of truth for the daily sweep.
    - `ingest_fuel_wa`, `ingest_fuel_nsw`, `ingest_fuel_qld` — per-state tasks operators can `.delay()` to retry a single feed without re-running the others.
  - When AUT-2374 lands the SA/TAS/NT ingesters they hook into `ingest_fuel_all` automatically; no further scheduler changes needed.
- feat(backend): `GET /api/v1/fuel/stations/{station_id}/history?days=30&fuel_type=...` — premium-gated, reads exclusively from the `fuel_prices` cache, never fans out to the upstream APIs. One 30-day series per fuel type, ascending `effective_at`.
- feat(backend): `_replace_station_prices` now **keeps the last 30 days** of price history instead of wiping the table on every ingest run. Upstream duplicates (same `fuel_type` + `effective_at`) are still replaced with the fresher value, then anything older than the retention window is pruned in one DELETE. Same `(station_id, fuel_type)` upsert semantics for the latest row.
- chore(backend): alembic migration `aut2375_fuel_history_index` adds `ix_fuel_prices_station_fuel_eff` on `(station_id, fuel_type, effective_at)` so the history endpoint serves without a sort step. Idempotent.
- test(backend): `tests/test_aut2375_daily_fuel_scheduler.py` is DB-free and asserts the history endpoint is premium-gated, the route is on the router, the beat schedule uses a cron (not a 6-hour interval), the timezone is `Australia/Sydney` with `enable_utc=False` (AUT-2402 B1), and the per-source tasks are registered.
## [0.3.231] - 2026-09-04
### Added (AUT-2448)
- backend(advisor): Ownership Advisor Finance module — deterministic buy / finance / lease (and novated-lease toggle, future-flagged). New `POST /api/v1/advisor/finance` route (per ADR 0001) takes `{down_payment, term_months, rate_pct, novated?}`, anchors `vehicle_price` on the value module's deterministic `mid` (so finance and value never disagree), and returns four mode blocks: `buy` (outright, zero monthly / interest), `finance` (standard amortising loan — full per-period schedule + total interest + total cost), `lease` (operating lease — residual % + residual value + money factor + monthly, scaled 25–75% across 12–60 month terms), and `novated` (gated by the `novated` request flag, always returns `status: "coming_soon"` until EV / FBT rules land in a follow-up ADR). Term is clamped per-mode (finance 12–84m, lease 12–60m); down payment caps at the vehicle price; zero-price vehicles emit a `note` instead of fabricating numbers. No 9Router / no AI — pure function `compute_finance_plan()` in `app.services.advisor`. New schemas `AmortizationRow`, `AdvisorFinanceModeBuy/Finance/Lease/Novated`, `AdvisorFinanceData`, `AdvisorFinanceRequest` in `app.schemas.advisor`. New `tests/test_advisor_finance.py` (19 cases: pure-helper amortisation / lease / residual / money-factor; per-mode shape; novated gating; term clamping; zero-price handling; zero-rate promo; textbook formula match).

## [0.3.230] - 2026-09-04
### Fixed (AUT-2481)
- frontend(servo-spy): dart2js compile error on `_cartoApiKey`/`_cartoKeyParam`. The two were declared as instance fields on `_ServoSpyScreenState` but referenced from `_ServoSpyMapState.build()` (different class, so name-resolution failed at compile time). Promoted both to file-private top-level `const` so both widget trees see them; removed the `const` from `_cartoKeyParam` (the runtime `isEmpty` check is not a constant expression).

### Fixed (AUT-2683)
- fix(backend): import `PowertrainType` in `app/schemas/vehicle.py` so the enum is defined before use. Missing import caused `NameError` at backend startup on every redeploy, returning 502 on all frontend requests.

### Added (AUT-2434)
- backend: vehicle powertrain field (`ICE | EV | HEV | PHEV`). New `PowertrainType` enum on `Vehicle` model with default `ICE`. Alembic migration `aut2434_vehicle_powertrain` adds `vehicles.powertrain VARCHAR(8) NOT NULL DEFAULT 'ICE'` — all pre-existing rows backfill to ICE. API responses (`VehicleOut`) now include `powertrain`; create/update accept `powertrain` in request bodies. Tests: `backend/tests/test_aut2434_powertrain.py` (6 offline cases: column present, enum locked to 4 tokens, Create/Update/Out serialization, default-ICE contract).

### Added (AUT-2445)
- backend(advisor): Ownership Advisor Vehicle Value module — deterministic market value with comparables and trade-in band. New `GET /api/v1/advisor/value` route (per ADR 0001) anchors on the cached `market_listing_cache` median (24h TTL, same as `/valuation/market`), applies a condition multiplier (excellent/good/fair/poor) and an odometer-vs-benchmark adjustment (±5% per 20k km off 15k km/yr benchmark, capped ±10%), surfaces a tight low/mid/high band, lists comparables (same make/model, year ±3y from the cache), and provides an industry-standard dealer trade-in band (75/82/90% of mid). Free accounts get 403; demo accounts allowed. New files: `backend/app/services/advisor.py` (deterministic helpers + comparables search + trade-in band), `backend/app/schemas/advisor.py` (shared `AdvisorResponse` envelope for all six advisor sub-modules), `backend/app/api/v1/advisor.py` (route). Tests: `backend/tests/test_advisor_value.py` (14 pure-helper tests covering condition/km multipliers, trade-in ratios, entitlement, envelope shape; 2 FastAPI route tests guarded by `pytest.skip` until the pre-existing `fuel_prices.py` `from __future__` syntax error is fixed — see AUT-2496).

### Added (AUT-2541)
- feat(backend): Home Assistant integration endpoints (`/api/v1/ha/*`). Per-user
  `abha_<token>` keys with sha256 digest storage + prefix index (mirroring the
  device-key pattern). User-managed token lifecycle (`POST/GET/DELETE /tokens`);
  HA-polled read-only sensors: `GET /v1/vehicles`,
  `/v1/vehicles/{id}/service-intervals`, `/v1/vehicles/{id}/analytics`, and
  `/v1/service-reminders` (all upcoming services across the user's cars). Auth
  via `X-HA-API-Key` header; vehicles shared with the user are included.
- docs: `docs/home-assistant-integration.md` — configuration + sensor/card
  examples for the `rest` + `rest.sensor` + `rest.select` platforms.

## [0.3.236] - 2026-09-05
### Fixed (AUT-2568)
- fix(deploy): frontend healthcheck in `docker-compose.yml`, `docker-compose.prod.yml`, and `docker-compose.hosted.yml` now references `${BACKEND_URL:-http://backend:8000}` (matching the existing `environment:` block) instead of bare `${BACKEND_URL}`, so compose interpolation can never resolve the URL to empty at deploy time (AUT-2350 follow-up: was producing `wget: bad address "/health"` and flipping the Portainer frontend container unhealthy). Also fixes the grep pattern from `"status": "ok"` to `"status":"ok"` so it matches FastAPI/ORJSON compact output `{"status":"ok",...}` — the with-space variant never matched and would silently re-break the healthcheck on a fresh redeploy from main. Repo now matches the stack actually running on EP5 (frontend Healthy).

## [0.3.235] - 2026-09-04
### Fixed (AUT-2467)
- fix(backend): resolve structlog `source` kwarg collision in `ingest_fuel_prices` (`app/workers/tasks.py:509`). `res` dict from `ingest_all_fuel` already contains a `source` key; passing `source=source` as a separate kwarg caused `TypeError: got multiple values for keyword argument 'source'`. Now logged as `logger.info("fuel_ingest_summary", **res)`. Also fixed `_run(_run())` in `run_due_checks` (`app/services/notify.py:257`) — inner `_run` had no args, so the coroutine was never scheduled. Renamed to `_coro` and routed through `tasks._run()`. Adds regression tests `test_ingest_fuel_prices_no_typeerror_when_source_in_result` and `test_run_due_checks_calls_check_for_each_vehicle`.

## [0.3.234] - 2026-09-04

### Fixed (AUT-2484)
- redeploy(homed): bump autobrain-backend :hosted-arm64 digest to include AUT-2277 duplicate-FuelPrice-class fix. EP5 was crash-looping on the pre-fix image (two `FuelPrice` classes claiming `fuel_prices` in `Base.metadata`). Source fix is already merged (f7db5b6d); rebuilt arm64 image from main `6e394007` and pinned the new digest in `docker-compose.hosted.yml`.

### Fixed (AUT-2469)
- fix(hosted, ci): replace standalone `myoung34/github-runner:latest` (amd64-only) on EP5 with a compose-managed `gh-runner` service using the official multi-arch `ghcr.io/actions/actions-runner:latest` (includes linux/arm64 binaries). The myoung34 image shipped amd64-only `.NET` binaries (`Runner.Listener`, `libcoreclr.so`); on the aarch64 Oracle VM the runner was in a permanent restart loop (`ldd: ./bin/libcoreclr.so: No such file or directory`), leaving ARM CI on Hosted dead. `build-hosted.yml` arm64 builds are unblocked. `docker/runner/entrypoint.sh` refreshes the short-lived runner registration token on every boot via the PAT secret file (AUT-1533 `*_FILE` pattern). `docker-compose.hosted.yml` now defines the `gh-runner` service; `scripts/seed-secrets.sh` seeds `github_pat` into the secrets dir. Deployment: stop the old standalone container before `docker compose up` to avoid a name collision (`docker stop gh-runner-autobrain-arm64 && docker rm gh-runner-autobrain-arm64`).

## [0.3.232] - 2026-09-04
### Fixed (AUT-2472)
- docker(ai): Playwright 1.62+ removed `chrome-sandbox` under `/ms-playwright` (kernel-namespace sandbox replaces SUID). The AUT-1739 `RUN find ... -name chrome-sandbox | chown root:root && chmod 4755` was failing every hosted build with `FATAL: no chrome-sandbox found`. Relaxed the guard: if at least one `chrome-sandbox` is found, re-SUID it; if none, log a warning and continue (the market-data scraper already falls back to `--no-sandbox` per `market-data/browser.py:81,158`). Keeps the build green and the AUT-2258 hard-fail behaviour when `chrome-sandbox` exists but is mis-owned.

### Added
- feat(fuel): AUT-2381 multi-source data-quality arbitration (best-price selection per station, SourceTrust enum)
### Fixed (AUT-2402 B1)
- fix(backend): `enable_utc=False` on the Celery app. AUT-2375 set `timezone="Australia/Sydney"` but left `enable_utc=True`, which forces Celery to interpret crontab schedules in UTC regardless of the `timezone` value — so `crontab(hour=2)` was firing at 02:00 UTC = 13:00 AEST, not the intended 02:00 AEST off-peak window. With `enable_utc=False`, the cron resolves in `Australia/Sydney` and the daily ingest lands at the intended wall-clock time. Test `test_celery_app_beat_uses_sydney_timezone_for_off_peak_cron` now asserts both `timezone == "Australia/Sydney"` and `enable_utc is False`.

### Fixed (AUT-2404)
- fix(backend): drop legacy `ingest-fuel-prices` beat entry from `app/workers/celery_app.py`. AUT-2375 added `fuel-ingest-all-daily` on the same 02:00 cron, so both fired daily and each upstream fuel feed (WA FuelWatch, NSW FuelCheck, QLD Fuel Prices) was hit twice per day for identical rows. Backwards-compat alias `ingest_fuel_prices = ingest_fuel_all` in `tasks.py` is preserved for dashboard / ad-hoc `.delay()` callers.

### Fixed (AUT-2403 rebase follow-ups)
- fix(backend): `app/services/fuel_prices.py` `from __future__ import annotations` moved to line 1 (was buried after the module docstring, line 188) so test_api / test_fuel_price_alerts can collect the module under Python 3.13. Pre-existing since PR #347 (AUT-1868) — surfaced by the AUT-2403 rebase because the smoke collection now hits the import path.
- fix(backend): add `FuelPriceWatchlistIn` / `FuelPriceWatchlistOut` pydantic schemas (`direction ∈ {up,down,both}`, `threshold_pct > 0`, defaults `both` / `5.0`). `backend/app/api/v1/fuel_prices.py` imports them since PR #347 but the schema definitions were never added, so 30+ test modules fail pytest collection (`cannot import name 'FuelPriceWatchlistIn'`).
- feat(backend): add `compute_price_change(price, previous)` pure helper to `app/services/fuel_prices.py` — day-over-day % move + up/down direction (AUT-1859). Returns `(None, None)` until both prices are present and previous is non-zero; zero delta is `(0.0, None)`. Used by `app/workers/tasks.py::check_fuel_price_alerts` (already importing it) and the watchlist unit tests.
- fix(backend): alembic migration `aut2375_fuel_history_index` `down_revision` rebased from `z2a3b4c5d6e7` to `aut2434_vehicle_powertrain` so the migration chain has a single head after AUT-2434 (vehicle powertrain) landed on main (originally `aut1859_fuel_price_alerts`, then `aut2434_vehicle_powertrain` once that migration reached main).

### Added (AUT-2375)
- feat(backend): Servo Spy fuel ingest now runs **once per day at 02:00 AEST** via Celery beat (`fuel-ingest-all-daily` cron, `timezone="Australia/Sydney"`, `enable_utc=False` so crontab schedules resolve in `Australia/Sydney` rather than UTC — see AUT-2402 B1). The previous 6-hour interval was over-fetching every upstream fuel API — every client request still served cached rows, but the schedule itself made a fresh API call four times a day for no UX gain. New schedule entries:
    - `fuel-ingest-all-daily` (`ingest_fuel_all`) — single source of truth for the daily sweep.
    - `ingest_fuel_wa`, `ingest_fuel_nsw`, `ingest_fuel_qld` — per-state tasks operators can `.delay()` to retry a single feed without re-running the others.
  - When AUT-2374 lands the SA/TAS/NT ingesters they hook into `ingest_fuel_all` automatically; no further scheduler changes needed.
- feat(backend): `GET /api/v1/fuel/stations/{station_id}/history?days=30&fuel_type=...` — premium-gated, reads exclusively from the `fuel_prices` cache, never fans out to the upstream APIs. One 30-day series per fuel type, ascending `effective_at`.
- feat(backend): `_replace_station_prices` now **keeps the last 30 days** of price history instead of wiping the table on every ingest run. Upstream duplicates (same `fuel_type` + `effective_at`) are still replaced with the fresher value, then anything older than the retention window is pruned in one DELETE. Same `(station_id, fuel_type)` upsert semantics for the latest row.
- chore(backend): alembic migration `aut2375_fuel_history_index` adds `ix_fuel_prices_station_fuel_eff` on `(station_id, fuel_type, effective_at)` so the history endpoint serves without a sort step. Idempotent.
- test(backend): `tests/test_aut2375_daily_fuel_scheduler.py` is DB-free and asserts the history endpoint is premium-gated, the route is on the router, the beat schedule uses a cron (not a 6-hour interval), the timezone is `Australia/Sydney` with `enable_utc=False` (AUT-2402 B1), and the per-source tasks are registered.
## [0.3.231] - 2026-09-04
### Added (AUT-2448)
- backend(advisor): Ownership Advisor Finance module — deterministic buy / finance / lease (and novated-lease toggle, future-flagged). New `POST /api/v1/advisor/finance` route (per ADR 0001) takes `{down_payment, term_months, rate_pct, novated?}`, anchors `vehicle_price` on the value module's deterministic `mid` (so finance and value never disagree), and returns four mode blocks: `buy` (outright, zero monthly / interest), `finance` (standard amortising loan — full per-period schedule + total interest + total cost), `lease` (operating lease — residual % + residual value + money factor + monthly, scaled 25–75% across 12–60 month terms), and `novated` (gated by the `novated` request flag, always returns `status: "coming_soon"` until EV / FBT rules land in a follow-up ADR). Term is clamped per-mode (finance 12–84m, lease 12–60m); down payment caps at the vehicle price; zero-price vehicles emit a `note` instead of fabricating numbers. No 9Router / no AI — pure function `compute_finance_plan()` in `app.services.advisor`. New schemas `AmortizationRow`, `AdvisorFinanceModeBuy/Finance/Lease/Novated`, `AdvisorFinanceData`, `AdvisorFinanceRequest` in `app.schemas.advisor`. New `tests/test_advisor_finance.py` (19 cases: pure-helper amortisation / lease / residual / money-factor; per-mode shape; novated gating; term clamping; zero-price handling; zero-rate promo; textbook formula match).

## [0.3.230] - 2026-09-04
### Fixed (AUT-2481)
- frontend(servo-spy): dart2js compile error on `_cartoApiKey`/`_cartoKeyParam`. The two were declared as instance fields on `_ServoSpyScreenState` but referenced from `_ServoSpyMapState.build()` (different class, so name-resolution failed at compile time). Promoted both to file-private top-level `const` so both widget trees see them; removed the `const` from `_cartoKeyParam` (the runtime `isEmpty` check is not a constant expression).

### Added (AUT-2434)
- backend: vehicle powertrain field (`ICE | EV | HEV | PHEV`). New `PowertrainType` enum on `Vehicle` model with default `ICE`. Alembic migration `aut2434_vehicle_powertrain` adds `vehicles.powertrain VARCHAR(8) NOT NULL DEFAULT 'ICE'` — all pre-existing rows backfill to ICE. API responses (`VehicleOut`) now include `powertrain`; create/update accept `powertrain` in request bodies. Tests: `backend/tests/test_aut2434_powertrain.py` (6 offline cases: column present, enum locked to 4 tokens, Create/Update/Out serialization, default-ICE contract).

### Added (AUT-2445)
- backend(advisor): Ownership Advisor Vehicle Value module — deterministic market value with comparables and trade-in band. New `GET /api/v1/advisor/value` route (per ADR 0001) anchors on the cached `market_listing_cache` median (24h TTL, same as `/valuation/market`), applies a condition multiplier (excellent/good/fair/poor) and an odometer-vs-benchmark adjustment (±5% per 20k km off 15k km/yr benchmark, capped ±10%), surfaces a tight low/mid/high band, lists comparables (same make/model, year ±3y from the cache), and provides an industry-standard dealer trade-in band (75/82/90% of mid). Free accounts get 403; demo accounts allowed. New files: `backend/app/services/advisor.py` (deterministic helpers + comparables search + trade-in band), `backend/app/schemas/advisor.py` (shared `AdvisorResponse` envelope for all six advisor sub-modules), `backend/app/api/v1/advisor.py` (route). Tests: `backend/tests/test_advisor_value.py` (14 pure-helper tests covering condition/km multipliers, trade-in ratios, entitlement, envelope shape; 2 FastAPI route tests guarded by `pytest.skip` until the pre-existing `fuel_prices.py` `from __future__` syntax error is fixed — see AUT-2496).

## [0.3.229] - 2026-09-04
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

### Added (AUT-2390)
- ci(security): `compose-config-diff` job in `.github/workflows/security-pr-gate.yml`. When a PR changes any `docker-compose*.yml`, the job runs `docker compose config` on both the PR and main versions (with a stubbed `.env.example`), extracts the set of referenced env-var keys, and blocks the PR on (a) any 1-edit / fuzzy-distance rename of an existing key (catches `AUTOBRIAN_BACKEND_URL` → `AUTOBRAIN_BACKEND_URL` and similar single-character typos that survive multiple deploys because `${NEW}` interpolates empty and `${OLD}` keeps its value), and (b) any new key not declared in `.env.example` (so reviewers know where to put the value). Wired into the `report-status` job's needs + Discord summary. Closes AUT-2390; closes the gap flagged by the AUT-1964 post-mortem.

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

### Added (AUT-2352, AUT-2353, AUT-2354)
- fix(frontend): boot-time reachability probe + debug banner for `AppConfig` (AUT-2352/2353/2354). Closes the three PR-#445 must-fix follow-ups from QA re-review.
  - `AppConfig.validate({http.Client?, timeout})` probes `${apiOrigin}/healthz` and populates `lastValidationOk` / `lastValidationError`. Caller-injected `http.Client` keeps tests hermetic. Default API/WS URLs now default to `https://hosted.autobrainservice.app` (the QA M3 finding: `localhost:8000` was a foot-gun for release builds).
  - `lib/main.dart` runs the probe in release builds only (`!kDebugMode` keeps hot-reload snappy); on failure it mounts a new `MisconfiguredBackendScreen` with a Retry button (`pushAndRemoveUntil` per AUT-2272 M2).
  - `MaterialApp.builder` returns a debug-only `Banner` in `app.dart` showing `API: …  WS: …  boot=ok|fail|not-run` for QA/dev to confirm the resolved backend at boot. Release builds pass `builder: null`.
  - `frontend/test/config_validation_test.dart` covers 2xx, 5xx, timeout, connection-refused, malformed URL, and empty `apiBase` against a `MockClient`.

### Security (AUT-1745)
- sec(market-data): `docs_url`, `redoc_url`, and `openapi_url` are now env-gated and default to disabled. When `ENVIRONMENT=production` (the hosted + prod compose default), `/docs`, `/openapi.json`, and `/redoc` all return 404 — closing the unauthenticated API-surface enumeration on the market-data FastAPI service (CWE-200). `/health` and authenticated `/search`, `/sca-parts` are unchanged. Regression covered by `market-data/test_docs_disabled.py` (prod: 404, non-prod: 200, /health always 200). `redoc` remains always-off by design. Companion fix in `CannonFodder151/rego-lookup-api` adds the same gating + test (PR #47).

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

### Added
- ci(libexpat): daily `libexpat-version-check` workflow resolves the current `nginxinc/nginx-unprivileged:stable-alpine` digest, reads the libexpat version via `apk info`, and auto-files a Paperclip issue with a PR-ready patch once the version reaches >= 2.8.4-r0 so the time-boxed `.trivyignore` entries (CVE-2026-66046, CVE-2026-76641) can be dropped (AUT-2126, AUT-2161).

## [0.3.205] - 2026-09-02

## [0.3.204] - 2026-09-02

### Fixed
- fix(docker, AUT-1978): rename typo `AUTOBRIAN_BACKEND_URL` → `AUTOBRAIN_BACKEND_URL` in `docker-compose.hosted.yml` dongle-server block (typo silently broke backend→dongle backchannel since the AUT-1673 dongle-server wiring landed).
- fix(docker, AUT-1978): remove the duplicated `dongle-server` service definition in `docker-compose.hosted.yml`. Docker Compose takes the LAST occurrence on duplicate keys, so the first block (plain `DONGLE_SERVER_API_KEY`, no MinIO/SECRETS_FILE wiring) was dead config; only the second block (with `_FILE` secrets anchor, AUT-2211 overrides) was live. Single source of truth restored.

## [0.3.214] - 2026-09-03

### Added (AUT-2218)
- chore(docker): wire `FUEL_QLD_API_KEY` into `docker-compose.prod.yml` backend block (mirrors NSW/VIC pattern; empty value disables the feed, see `backend/app/services/fuel_feeds.py:493`).
- chore(docker): wire `FUEL_QLD_API_KEY_FILE: /run/secrets/fuel_qld_api_key` into `docker-compose.hosted.yml` backend + worker blocks. The existing `x-secrets` anchor (`<<: *secrets`) already bind-mounts `${SECRETS_DIR}` read-only, so no new volume entry is required; seed `fuel_qld_api_key` via `scripts/seed-secrets.sh` before redeploying the hosted stack.

### Fixed (AUT-1946)
- fix(backend): bake EXIF orientation into pixels on social photo uploads (`ImageOps.exif_transpose`) so phone portraits stored as webp no longer display sideways — webp has no EXIF, so the orientation must be baked at upload time.
- fix(frontend): add a per-photo rotate (90° CW) button in the Edit Build screen so portrait shots that come in sideways can be rotated before saving. Existing-stored photos (URL only) skip rotate since the backend fix already corrects them at upload time.

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

### Security
- Re-pin frontend nginx base image (`nginxinc/nginx-unprivileged:stable-alpine`) by
  `@sha256` digest in `docker/frontend/Dockerfile` (AUT-1600 branch rebase — the
  AUT-2087 digest re-pin was missing on the Redis-healthcheck branch).
- Bump `pypdf` from `6.15.0` → `6.16.1` in `backend/requirements.txt` and
  `ai/requirements.txt` to clear CVE-2026-84309 / CVE-2026-84310 / CVE-2026-84311
  flagged by the PR-time pip-audit gate (AUT-1600 branch rebase — main was
  already on 6.16.1).
- Suppress trivy 0.70 placeholder CVE-2026-80256 in `.trivyignore` — the
  nginx frontend image's vuln DB entry has no metadata yet (trivy logs
  "no vulnerability details" and exits 1 on the metadata miss). Trivy 0.74 +
  a fully populated DB will resolve it; this entry can be dropped after.

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
