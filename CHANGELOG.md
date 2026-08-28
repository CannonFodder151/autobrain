# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.


## [Unreleased]


### Security
- Hardened Redis in `docker-compose.prod.yml` — added `--requirepass` and updated healthcheck to authenticate; environment variable `REDIS_PASSWORD` is now required (AUT-1600).


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
