# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.















## [Unreleased]

### Added
- Community Garage backend (AUT-332): social models/API/media under `backend/app/social/` — build posts (vehicle snapshot from existing specs + mods, deterministic — no AI), photo upload with on-upload webp compression + signed short-lived MinIO URLs, comments, likes, share links, and a federation hub client (register / outbox / inbox; the hub itself ships separately). Routes: `/social/feed`, `/social/posts`, `/social/posts/{id}/comments`, `/social/posts/{id}/likes`, `/social/posts/{id}/share-link`, `/social/uploads`.
- Premium entitlement guard on all social routes (rev 4): free accounts are locked out server-side; demo accounts keep read-only access.
- Two admin toggles via `/admin/social` (GET/PATCH + register/unregister): federated on/off (off = local-only feed, no hub calls) and feature on/off (off = "Disabled by your admin"). Overrides persist in `social_server_config`, seeded from env settings.
- Demo seeding (req 10): `DEMO_MODE` seeds curated demo builds (feature on, federation off) with a demo photo.
- `pillow` pinned in backend requirements; social tables added to the backup/restore order and user-deletion cleanup.

## [0.3.19] - 2026-08-11

### Security
- MinIO bucket no longer anonymously readable (AUT-321): `autobrain-assets` anonymous `download` policy removed from `docker-compose.hosted.yml` and `scripts/init-minio.sh` (init now forces `anonymous set none`). `upload_object` returns a 1-hour presigned GET URL instead of a world-readable URL, and the frontend nginx proxies `/autobrain-assets/` to MinIO while preserving the signed Host header. Existing buckets are re-privatized on redeploy.

## [0.3.18] - 2026-08-11

### Fixed
- Frontend nginx now re-resolves the `backend` upstream via Docker's embedded
  DNS (`resolver 127.0.0.11` + variable `proxy_pass`) so public `/health`,
  `/api/` and `/ws/` survive backend container recreates without a manual
  frontend restart (AUT-373).

## [0.3.17] - 2026-08-11

### Added
- Public `GET /api/v1/version/mobile` endpoint that reports the latest
  published `autobrain-mobile` release (read from GitHub server-side, since the
  mobile repo is private). The mobile app consumes it via the connected server
  for its version banner (AUT-365).

## [0.3.16] - 2026-08-11

### Fixed
- Hosted/Default blank page (AUT-347): the CSP allowlisted `www.gstatic.com` but not `fonts.gstatic.com`, so CanvasKit's startup font fetch stalled the Flutter engine before the first frame. `fonts.gstatic.com` is now allowed in `font-src` + `connect-src`; text/images render again.

## [0.3.15] - 2026-08-11

### Fixed
- Car valuation now reports `market-anchored` (not `rule-based-fallback`) when live market listings anchor the estimate (AUT-354).

## [0.3.14] - 2026-08-11

### Fixed
- Version banner inverted (AUT-346): a server behind the repo (e.g. v0.3.6 vs repo v0.3.10) was shown as "Up to date"; the `up_to_date` comparison was reversed. The banner now correctly reports "Update available" when the running server is behind.

## [0.3.13] - 2026-08-11

### Added
- Market-data browser channel (AUT-314): a Playwright chromium worker (`market-data/browser.py`, subprocess pattern mirrored from rego-lookup-api) is wired behind the BikeGuide provider so the FingerprintJS-gated motorcycle portal gets a real-browser scrape path. Plain HTTP still runs first (fast), the browser only spawns when the page looks like a live gate, and every path degrades to a deterministic empty listing set + `note` — valuations never error. Both AU motorcycle portals were probed with a real Chromium browser: `bikesguide.com.au` is a parked/for-sale domain (no listings exist) and `bikesales.com.au` sits behind a PerimeterX hold-to-confirm challenge that does not clear from the dev/hosted networks; motorcycle valuations therefore stay on the deterministic degradation path (`sample_size=0`) until a portal opens.

### Fixed
- Market-data parser (AUT-314): `carsguide._parse_nuxt_listings` crashed with `AttributeError: 'list' object has no attribute 'get'` when a query returned `marketplace` as a list (e.g. motorcycle searches on carsguide.com.au). Non-dict `marketplace` values are now treated as "no listings" instead of 500ing the scraper.
- Market-data browser worker (AUT-314): the Playwright worker passed the search query via a non-existent `page.goto(params=...)` kwarg, so the BikeGuide browser channel failed with `TypeError`. The search URL is now built with `urlencode`; the channel verifiably reaches the parked-page path.

## [0.3.12] - 2026-08-11

### Security
- Rego provider logs redacted (AUT-324): `rego_provider_lookup` logs only mapped fields (make/model/year/status) instead of the raw provider payload, so registration data and VINs never reach log storage.

## [0.3.11] - 2026-08-11

### Fixed
- Hosted/default blank white screen (AUT-339): frontend CSP now allowlists `https://www.gstatic.com` in `script-src`/`connect-src`/`img-src`/`font-src` so the Flutter CanvasKit engine bundle can load; previously `script-src 'self'` and `connect-src 'self'` blocked `canvaskit.js`/`canvaskit.wasm`, so the web app never bootstrapped.

## [0.3.10] - 2026-08-11

### Fixed
- Alembic migration chain (AUT-290): `market_listing_cache` and the HNSW embedding-index migrations shared the same revision id `h1i2j3k4l5m6`, which broke `alembic upgrade head` (boot fell back to `create_all`, leaving `users.pending`/`users.token_version` and other columns unapplied). Renamed the market-cache revision to `h1i2j3k4l5m7` and folded it into the `m3rge01` merge so the chain has a single head.

## [0.3.9] - 2026-08-11

### Added
- Market-data scraper API (AUT-290): self-hosted `market-data` service scrapes live CarsGuide listings (no browser, via the site's SSR `__NUXT_DATA__` payload) and serves `POST /search` with `{query, make, model, year}` behind an API key — the same protocol rego-lookup uses. Wired into the hosted stack as `MARKET_DATA_URL`/`MARKET_DATA_API_KEY`, so valuations now anchor on real listings instead of showing "provider not configured".

## [0.3.8] - 2026-08-11

### Added
- Live used-car market data for valuations (AUT-287): resale estimates now anchor on real CarsGuide/CarSales listings fetched through a self-hosted market-data API (`MARKET_DATA_URL` + `MARKET_DATA_API_KEY`), cached 24h per make/model/year so repeated valuations return identical numbers. `GET /api/v1/vehicles/{id}/valuation/market` returns the listings + median/low/high aggregates; `.../valuation/market/search` searches live listings. When no provider is configured the deterministic model + AI advice path still runs with `source=fallback`.

## [0.3.7] - 2026-08-11

### Added
- OBD-II integration (mobile-only, AUT-272): connect a Bluetooth ELM327 adapter (tested with VGate iCar Pro) from the OBD screen — adapter picker, connect + auto-connect toggle, live PID polling every 2s, fault-code read (modes 03 + 07, deduped to the backend) and VIN autofill on connect. The ELM327 protocol layer is pure Dart with 22 golden-adapter unit tests.

## [0.3.6] - 2026-08-10

### Added
- MinIO asset backup/restore admin endpoints (AUT-194): `GET /admin-api/assets/backup` streams a tar.gz of every object in the MinIO bucket, `POST /admin-api/assets/restore` validates + restores a gzip tar before wiping,    enabling the autobrain-backup service to back up DB snapshots and image assets together.

### Changed
- Automatic release cutting (AUT-240): `scripts/auto-bump.sh` now runs before
  every app/docker build — in CI (`dockerhub-publish.yml`, `build-hosted.yml`)
  and local (`publish-images.sh`, `deploy.sh`). Whenever `CHANGELOG.md` has a
  non-empty `[Unreleased]` section, it bumps the patch version
  (`x.y.z` → `x.y.(z+1)`) via `bump-version.sh`, re-opens `[Unreleased]`, and
  commits the release — so a change can never ship without a new version.
  Images are additionally tagged with the release version (e.g. `0.3.6`).
  No AI agent needed: a deterministic gate is more reliable than an LLM for
  this, matching the "deterministic paths first" rule.
- Changelog is now mandatory for every app/docker change (AUT-168): CI on
  `main` fails the Docker Hub publish if `backend/`, `ai/`, `frontend/`,
  `docker/` or compose files changed without a matching `CHANGELOG.md` entry.
  The marketing site still auto-syncs `CHANGELOG.md` and regenerates
  `changelog.html` on every release push, so the website changelog always
  reflects the shipped code.

### Fixed
- Security headers (AUT-234/236): frontend nginx now sends `Content-Security-Policy`, `X-Frame-Options: DENY` and `Referrer-Policy` on all responses, closing the ZAP CSP + clickjacking findings on `default.autobrainservice.app`; CSP is tuned for the Flutter web renderer (`'wasm-unsafe-eval'`, same-origin `connect-src`).
- Security (AUT-234/236): server-picker example host changed from `192.168.1.100` to `192.0.2.1` (RFC 5737 TEST-NET-1) so the built `main.dart.js` no longer embeds an RFC1918 private IP.
- Asset backup no longer fails on zero-byte MinIO directory-marker objects (`obj.is_dir`/keys ending in `/`): `export_assets` skips them instead of hitting `NoSuchKey` (AUT-194).
- Security: `/ws/{user_id}` WebSocket now requires a valid access JWT and fail-closes; search embedding SQL is bound-parameterized (`CAST(:embedding AS vector)`) instead of interpolated; `/api/v1/search` results are scoped to the requesting user's owned + shared vehicles (IDOR fix) (AUT-203, AUT-134).

## [0.3.5] - 2026-08-09

### Added
- Vehicle sharing (AUT-16/AUT-21/AUT-115): share a vehicle with another AutoBrain account by email (3-dot menu on the vehicle card). Pending invites sit in an **Invited** section with Accept/Deny, shared vehicles show an "(Invited by <name>)" label, and owners can remove access at any time. Available in both the web and mobile apps.
- Feature gating follows the car's owner (AUT-21): a free account invited to a paid owner's vehicle inherits the owner's AI and rego entitlement on that car; a free owner still blocks those features for everyone, including invitees.

### Changed
- Versioning unified around a single `x.y.z` (see `docs/versioning.md`): the backend and AI gateway report `APP_VERSION` (no more stale hardcoded strings), and `bump-version.sh` updates backend, AI gateway, web, mobile and the changelog in one shot.
- Public `GET /api/v1/auth/config` now returns `app_version` so the mobile app can detect when it is behind and prompt for an update on login.
- Stripped sensitive info from the repo (sample number plate in the changelog, internal IPs, hostnames and hosting details in `.env.example`, config defaults, compose comments and docs).

## [0.3.4] - 2026-08-06

### Added
- Rego lookup now sends the vehicle type (car/motorcycle) to the self-hosted scraper. VIC motorcycles resolve correctly — the vicroads form selects the motorcycle field and vehicle-type dropdown (test case: `[redacted]` → clean not-found for an unregistered plate).
- Motorcycle-aware offline fallback — a bike never falls back to a guessed car.
- Vehicle type is enforced in the add/edit vehicle screens before rego lookup (selector moved above the rego field).

### Fixed
- Scraper no longer misreads form dropdown labels (e.g. "Chassis number") as result data.
- Provider timeout raised to 150s so a retrying browser lookup completes instead of falling back early.

## [0.3.3] - 2026-08-06

### Added
- Vehicle type: every vehicle is a Car or a Motorcycle (dropdown on add/edit). The home screen shows a motorcycle icon for bikes, and the vehicle type is passed to the AI agents (diagnostics, service prediction, valuation, mod impact).
- Admin console: search users by display name or email — alphabetical, 15 per page, with previous/next buttons.
- Account creation (signup + admin) rejects duplicate emails and duplicate display names.
- "Delete account" menu item for non-admin users on licensed servers, linking to the deletion instructions page.
- Demo data: two motorcycles plus logbook trips, scanned receipts, valuations and diagnostics.

### Fixed
- Service/mod `photo_keys` now store as JSON (raw-list inserts from the receipt auto-apply flow and the demo seed previously failed).
- Web home screen no longer shows garbled characters on the vehicle display.
- Admin user list no longer 500s — `UserAdminOut` now serializes ORM rows (blank list / broken search fixed).
- CSV exports now include a UTF-8 BOM so Excel renders em-dashes and unicode correctly instead of garbled characters.
- Home screen shows a clear "server unreachable" error (with Retry) instead of "no vehicles" when the backend is offline.

## [0.3.2] - 2026-08-06

### Changed
- Android app distributed via Google Play (`com.autobrainservice.app`); the
  in-app "Get the mobile app" download dialog and menu item are removed.
- Mobile: sign out now offers "Sign out & change server"; new app icon.
- Rego lookup resilience: provider timeout raised to 90s (covers the
  scraper's fast-fail + retry).

## [0.3.1] - 2026-08-06

### Fixed
- Fuel efficiency (L/100km, cost/km) now calculates when you back-fill an
  older fill-up. The full-tank efficiency chain is recomputed after every
  add/edit/delete, so later fills are re-chained correctly; out-of-order or
  duplicate odometer entries stay blank instead of getting a wrong value.

## [0.3.0] - 2026-08-06

### Added
- Fuel tracker: filter the list by Australian financial year, and export by
  FY as CSV or CSV + receipt images (ZIP). Scanned receipts are saved against
  the fuel record (receipt_id) and exported alongside it.
- Service history and build sheet exports support `fmt=zip`: CSV gains an
  Image column and the receipt/scan photos are bundled in the ZIP.
- Receipt scans auto-attach their image to the service record created from
  the scanner (`photo_keys` on `service_records`).
- Admin console: "Re-upgrade" action grants the $19/month Enthusiast
  benefits to an account without a Stripe subscription, and sponsored
  accounts are blocked from buying a licence.
- Licence/upgrade feature is gated behind `LICENSE_ENABLED` (served via
  `GET /auth/config`). On for the hosted instance, off for demo/default and
  self-hosted; the app hides the License page when disabled.
- Self-hosted rego lookup: `REGO_LOOKUP_URL` now points at the
  Plate-API-Scraper (POST `/lookup`) instead of the paid plateapi provider.

### Fixed
- Fuel receipts no longer stay stuck on `pending` when OCR is unavailable
  (the record is marked done/failed and the image stays usable).
- Removed the odometer photo-scan option from the logbook.

## [0.2.4] - 2026-08-05

### Added
- `SELF_SIGNUP_ENABLED` now also drives the UI: the app fetches public `GET /auth/config` (`signup_enabled`) and hides the "Create a free account" button when disabled. Signup stays on by default for the hosted instance and is disabled on demo/default (admin-provisioned).

## [0.2.3] - 2026-08-05

### Fixed
- Receipt uploads: the app now sends a real file MIME type (it previously always sent `application/octet-stream`, which the fuel-receipt endpoint rejected with "unsupported file type").
- Backend now sniffs file type from magic bytes (PDF/JPEG/PNG/WEBP) before trusting the upload header, so photos from phone/camera pickers work for fuel receipts, receipts scanner and odometer OCR. HEIC/TIFF now accepted too.

## [0.2.2] - 2026-08-05

### Fixed
- Web autofill: removed the global Enter-key interceptor that could swallow browser password-manager fills (Enter still submits via the fields themselves).
- MFA code fields now carry `one-time-code` autofill hints so browsers offer the OTP/password suggestion (login, MFA setup, and Settings & security).

## [0.2.1] - 2026-08-05

### Added
- Vehicle body type field (add/edit form, rego-lookup auto-fill, shown on vehicle cards and home screen).

## [0.2.0] - 2026-08-05

### Added
- Vehicle colour field (add/edit form, rego-lookup auto-fill, shown on vehicle cards and home screen).
- Self-service Free-tier signup (hosted): display name + email only; a 7-day setup email completes the account (choose password + MFA, enforced on the hosted instance).
- Stripe self-service billing: Checkout, Customer Portal, cancel-at-end-of-period, webhook promote/demote between free and paid plans.
- OBD2 hardware companion listed as a **Coming soon** product on the marketing site (not part of subscription plans).
- ATO logbook: per-trip logging for non-club-reg vehicles (start/end time, GPS, odometer, work/private, reason), edit/complete trips, per-financial-year CSV export, and dashboard-photo odometer OCR (AI). Completing a trip updates the vehicle odometer.
- Club registration selector on vehicles — club-registered vehicles disable the logbook feature.
- Fuel: edit/delete fill-ups, fuel-receipt photo upload (AI parse of litres/price-per-litre, or plain upload without AI), and per-financial-year CSV export for tax purposes. Fuel always updates the odometer unless a newer logbook trip governs.
- Free account tier (`free_account` per user): disables AI features and rego lookup (403 server-side); file exports are available on all plans.
- Server version in admin settings with GitHub latest-release check (up to date / update available).
- Diagnostics: resolve + delete once fixed; a diagnostic auto-flips to resolved (green tick) when its linked scheduled service is completed.
- Profile export/import: download your whole account as JSON and import it on any server.
- Admin backup & restore: full JSON database snapshot download, wipe-and-restore endpoint, and a scheduled daily backup (Celery beat → MinIO) with retention.
- Admin API key (`ADMIN_API_KEY` + `X-Admin-API-Key`): create users, set permissions (role, vehicle quota, free/paid account, OBD access), list, disable and delete users machine-to-machine.
- OBD-II seam: fault-code library with save/pull-to-AI-diagnostics, VIN auto-fill, admin-gated per-account access, Bluetooth auto-connect setting, and a "work in progress" UI for the live adapter features.
- AI gateway: new `fuel-ocr` and `odometer` modules; all modules run at temperature 0 with validated/clamped numeric output (resale low ≤ est ≤ high) for stable estimates.
- Azure/cloud web build fix: hermetic `pub get` (pubspec.lock copied) and removed the vestigial `build_runner` step.
- Live 9Router integration: OpenAI-compatible router client (`AI_ROUTER_URL`/`AI_ROUTER_MODEL`), per-module strict-JSON prompts, tolerant schemas.
- Web app delivery: Flutter web build served at `/` behind the proxy nginx.
- TOTP multi-factor authentication (setup QR, enable/disable, MFA-gated login) and self-service password reset.
- Role-based access (admin/user) with admin user management and seeded bootstrap admin.
- Australian rego lookup (state-aware, personalised-plate word decoding, optional plateapi.com.au provider).
- Services overhaul: scheduled/completed status, editable service cards with items + work steps, AI prediction, PDF/CSV export.
- Receipt & parts OCR, parts inventory with AI reorder suggestions, resale value estimator, analytics.

### Fixed
- Login: email field is focused and its text selected on page load (fixes the web-autofill landing issue).
- Login/MFA: the 6-digit verification code field is auto-focused when the MFA step appears.
- Login/MFA: pressing Enter on the keyboard now submits the form instead of doing nothing.
- Login: completing MFA setup no longer leaves the button spinning — the busy state is cleared and the app returns to the home screen.

### Changed
- Free accounts can export files; only AI features and rego lookup remain paid.
- MFA is no longer a paid-plan feature — available on all tiers.
- Self-service signup collects display name + email only; a setup email completes the account (password + MFA).

### Removed
- GitHub Actions CI/CD workflows.
- Initial AutoBrain scaffold.
