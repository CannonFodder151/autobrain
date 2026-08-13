# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.
































## [Unreleased]

### Security
- Crafted-PDF DoS regression tests (AUT-471): new `backend/tests/test_pdf_dos_regression.py` feeds the receipt worker `_pdf_text()` oversized CID `/W` width ranges (GHSA-fwg2-594c-jp42) and large `/ToUnicode` CMaps (GHSA-fp3f-mc75-235c) and asserts fast rejection. Both runtime requirement files stay pinned to `pypdf==6.15.0` (the fix release); the existing pin-guard test enforces it.

## [0.3.37] - 2026-08-13

### Security
- Private-repo clones now use SSH read-only deploy keys instead of a PAT (AUT-461); the classic PAT is limited to agent-side `gh` API automation.

## [0.3.36] - 2026-08-13

### Security
- Version-check (AUT-461): GitHub token removed from the server entirely. The private `autobrain-mobile` release check no longer calls the GitHub API with a PAT — the release info is published to a public manifest (`mobile/latest.json` in the autobrain repo) and read unauthenticated. `GITHUB_TOKEN` deleted from backend config, compose files, and stack envs; legacy classic PAT no longer exposed at runtime.

### Changed
- `/api/v1/version/mobile` now reads the mobile release from `mobile/latest.json` (public repo) instead of the private repo's GitHub API. Deploy pipeline updates that manifest on each mobile release; no server redeploy needed for manifest updates.

## [0.3.35] - 2026-08-13

### Added
- Community Garage backend (AUT-332): social models/API/media under `backend/app/social/` — build posts (vehicle snapshot from existing specs + mods, deterministic — no AI), photo upload with on-upload webp compression + signed short-lived MinIO URLs, comments, likes, share links, and a federation hub client (register / outbox / inbox; the hub itself ships separately). Routes: `/social/feed`, `/social/posts`, `/social/posts/{id}/comments`, `/social/posts/{id}/likes`, `/social/posts/{id}/share-link`, `/social/uploads`.
- Premium entitlement guard on all social routes (rev 4): free accounts are locked out server-side; demo accounts keep read-only access.
- Two admin toggles via `/admin/social` (GET/PATCH + register/unregister): federated on/off (off = local-only feed, no hub calls) and feature on/off (off = "Disabled by your admin"). Overrides persist in `social_server_config`, seeded from env settings.
- Demo seeding (req 10): `DEMO_MODE` seeds curated demo builds (feature on, federation off) with a demo photo.
- `pillow` pinned in backend requirements; social tables added to the backup/restore order and user-deletion cleanup.

## [0.3.34] - 2026-08-13

### Security
- Version-check (AUT-442): GitHub PAT no longer attached to public `autobrain` server-version checks; token now sent only for the private `autobrain-mobile` release check. Use a fine-grained read-only token scoped to `autobrain-mobile` only.

## [0.3.33] - 2026-08-13

### Changed
- Deployment (AUT-450): hosted stack `docker-compose.hosted.yml` now references Docker Hub images (`cannonfodder151/autobrain-*:hosted`, matching the live stack) and pins the backend to static IP `172.18.0.15` (AUT-439). Deploy log added to `docs/deployment-guide.md`.

## [0.3.32] - 2026-08-13
### Fixed
- Alembic migration chain (AUT-450): `a5b6c7d8e9f0` (logbook `gps_samples`, AUT-395) referenced a never-existent down_revision `n4p5q6r7s8t9`, so `alembic upgrade head` crashed with `KeyError` on every boot, the create_all fallback silently skipped it, and the `source` column (AUT-362) never applied on fresh DBs (demo/hosted) — demo seed then crash-looped. Reparented to `k2l3m4n5o6p7` so the chain is linear and both columns apply.

## [0.3.31] - 2026-08-13
### Security
- Dependency bump (AUT-301): `pypdf` pinned `6.14.2` → `6.15.0` in `backend/requirements.txt` and `ai/requirements.txt`, fixing two DoS CVEs in crafted-PDF parsing (CVE-2026-71852 large CID font width ranges, CVE-2026-71870 large /ToUnicode streams) reachable via user-uploaded receipt PDFs in the Celery worker.

### Added
- Logbook trip routes on a map (AUT-395): trips recorded with GPS now carry a deterministic polyline of `lat,lon` samples (`logbook_entries.gps_samples`, JSON). Phone/car-kit auto trips buffer fixes while driving (survive app kills; ~1 fix/s, capped) and sync them on completion; the board CSV schema `epoch,...,lat,lon` (raw degrees x10^7, `0,0` = no fix) is a valid source via `backend/app/services/trip_gps.py::parse_board_csv` (invalid/out-of-range fixes dropped server-side — no AI). The logbook shows a "View route" button per trip → a full-screen OpenStreetMap route (flutter_map) with start/end markers, skipping no-fix samples. Detail endpoint `GET /vehicles/{id}/logbook/{entry_id}` returns `gps_samples` so the list stays light.

## [0.3.30] - 2026-08-13


### Added
- Logbook trip routes on a map (AUT-395): trips recorded with GPS now carry a deterministic polyline of `lat,lon` samples (`logbook_entries.gps_samples`, JSON). Phone/car-kit auto trips buffer fixes while driving (survive app kills; ~1 fix/s, capped) and sync them on completion; the board CSV schema `epoch,...,lat,lon` (raw degrees x10^7, `0,0` = no fix) is a valid source via `backend/app/services/trip_gps.py::parse_board_csv` (invalid/out-of-range fixes dropped server-side — no AI). The logbook shows a "View route" button per trip → a full-screen OpenStreetMap route (flutter_map) with start/end markers, skipping no-fix samples. Detail endpoint `GET /vehicles/{id}/logbook/{entry_id}` returns `gps_samples` so the list stays light.

## [0.3.28] - 2026-08-13
### Added
- "Car Play / Android Auto Integration" settings submenu (AUT-366, mobile-only): honest explainer of what works (auto trip logging) vs what doesn't (head-unit OBD gauges, CarPlay OBD — Google/Apple category policy + Android-only Bluetooth SPP stack), an "Auto-start trip logging when connected to the car" toggle (wired to the OBD adapter car-connection service), and a live connection / last-trip status line. Hidden on web.
- OBD automatic trip recording (AUT-362, Android): GoFar-style auto start/stop logbook trips. With the VGate iCar Pro adapter left in the car and `Auto-connect OBD` on, a foreground service keeps the app alive in the background, ignition is detected from battery voltage (PID 0142) + engine RPM (010C) + BT link-drop, and each drive lands in the logbook automatically — marked "auto (OBD)" so manual trips stay distinguishable. A mid-drive app kill no longer loses a trip (buffered locally, synced on next open). Backend: `logbook_entries.source` column (`manual`/`obd_auto`) via Alembic migration.
- Phone-side auto trip logging (AUT-367, Android): auto start/stop logbook trips with no OBD adapter and no Android Auto approval. When the phone links to the car's Bluetooth (head-unit / car-kit) a trip is armed, then starts once GPS speed is sustained above a threshold (a passenger in a bus never starts one); the link dropping or the car going quiet stops and closes the trip with distance from the GPS odometer diff. Both this phone path and the VGate/OBD path (AUT-362) drive one shared auto start/stop recorder. Backend: `source=car_auto` trips and caller-provided `distance_km` accepted on logbook update. Logbook marks these "auto (car kit)".
- Logbook screen (mobile + web): auto-logged trips are labelled "auto (OBD)" / "auto (car kit)" in the trip list.

### Fixed
- Version banner inverted (AUT-346): a server behind the repo (e.g. v0.3.6 vs repo v0.3.10) was shown as "Up to date"; the `up_to_date` comparison was reversed. The banner now correctly reports "Update available" when the running server is behind.
- "Get the mobile app" no longer shows inside the mobile app (AUT-428): the home-screen menu item and its download dialog are now hidden on Android/iOS builds and only offered on the web app, where downloading the app actually makes sense.


## [0.3.27] - 2026-08-13
### Added
- "Car Play / Android Auto Integration" settings submenu (AUT-366, mobile-only): honest explainer of what works (auto trip logging) vs what doesn't (head-unit OBD gauges, CarPlay OBD — Google/Apple category policy + Android-only Bluetooth SPP stack), an "Auto-start trip logging when connected to the car" toggle (wired to the OBD adapter car-connection service), and a live connection / last-trip status line. Hidden on web.
- OBD automatic trip recording (AUT-362, Android): GoFar-style auto start/stop logbook trips. With the VGate iCar Pro adapter left in the car and `Auto-connect OBD` on, a foreground service keeps the app alive in the background, ignition is detected from battery voltage (PID 0142) + engine RPM (010C) + BT link-drop, and each drive lands in the logbook automatically — marked "auto (OBD)" so manual trips stay distinguishable. A mid-drive app kill no longer loses a trip (buffered locally, synced on next open). Backend: `logbook_entries.source` column (`manual`/`obd_auto`) via Alembic migration.
- Logbook screen (mobile + web): auto-logged trips are labelled "auto (OBD)" in the trip list.


## [0.3.26] - 2026-08-13
### Fixed
- AI service prediction now uses the selected vehicle (AUT-398): the prediction screen fetched `GET /vehicles` and used the first entry, so it could predict for the wrong car (e.g. the Fazer) when the crown-selected vehicle was not first in the list. It now fetches `GET /vehicles/{id}` for the vehicle the user opened from.

## [0.3.25] - 2026-08-13
### Security
- AI rate limiting (AUT-302): every AI endpoint (diagnostics, service prediction, valuation, mod impact, odometer OCR, receipt OCR, fuel-receipt OCR) now enforces per-user burst + daily caps via Redis (defaults 10/min and 50/day, env-tunable) and returns `429` on exceed. The AI gateway adds an in-memory per-IP + global window as defense in depth. Fails closed (503) if Redis is unreachable so un-metered 9Router spend is never possible.

## [0.3.24] - 2026-08-13
### Added
- OBD clear codes (AUT-360): `DELETE /vehicles/{id}/obd/codes` clears every saved fault code for a vehicle (per-code delete unchanged). Mobile OBD screen gets a "Clear codes" action on the saved fault codes library (with confirmation) and on the live adapter card, which sends ELM327 mode 04 to clear the ECU's stored DTCs and re-reads the codes.

## [0.3.23] - 2026-08-13
### Fixed
- OBD is hidden on web builds (AUT-364): Bluetooth Classic SPP is Android-only, so the home-screen OBD tile and the Settings "OBD features" chip no longer render on the Flutter web app (kIsWeb-gated). Mobile (autobrain-mobile) OBD is untouched.


## [0.3.22] - 2026-08-13
### Fixed
- Security (AUT-303): login brute-force rate limit was bypassable by spoofing `X-Forwarded-For` (the backend trusted the client-controlled leading hop, so an attacker could rotate the header and never hit `LOGIN_MAX_ATTEMPTS`). The client IP is now derived from the trusted proxy header `X-Real-IP` (nginx sets `X-Real-IP $remote_addr`) and never from `X-Forwarded-For`. Failure counters moved from process memory to Redis (shared across workers, survive restarts) and now also count per-email as defense in depth against a misconfigured proxy.


### Changed
- OBD VIN updates are manual only (AUT-361): connecting the adapter no longer silently writes the stored VIN. The OBD screen's Vehicle VIN card gains an **Update VIN** button that reads mode 09 PID 02 and saves it behind a confirmation, with busy + success/failure feedback (manual "Set VIN" entry kept). `POST /vehicles/{id}/obd/vin` now replaces an existing VIN instead of rejecting it with 409.

### Fixed
- Hosted frontend now pins a static container IP (172.18.0.14) on the pinned default network (AUT-372): host-level nginx-proxy-manager caches the frontend's resolved IP, so a recreated frontend with a new IP returned 502 until npm was restarted. Frontend recreates now keep the same IP and the site stays up with no npm restart.

## [0.3.21] - 2026-08-12

### Fixed
- AI service prediction now predicts for the selected vehicle (AUT-429): it always used the first vehicle in the list, so with a different vehicle selected (e.g. your Crown) it showed the wrong one (e.g. your Fazer).

## [0.3.20] - 2026-08-12

### Fixed
- "Get the mobile app" menu item no longer shows on the mobile app itself (AUT-399): `HomeScreen` only renders the download entry when not running natively on Android/iOS. `AppConfig._isMobile` → public `AppConfig.isMobile`.

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
