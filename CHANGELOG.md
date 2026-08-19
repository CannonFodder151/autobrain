# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.







## [Unreleased]

### Changed
- App logo asset (AUT-1153): updated `frontend/assets/logo.png` with refreshed AutoBrain branding.

## [0.3.104] - 2026-08-18

### Changed
- Hosted app images (AUT-1114): `docker-compose.hosted.yml` now pulls `backend`, `ai`, `market-data` and `frontend` images from `ghcr.io/cannonfodder151/*:hosted` (multi-arch, incl. arm64) instead of Docker Hub, which only carries amd64 `:hosted` tags (AUT-967). The Oracle host is arm64, so Docker Hub image pulls could run the wrong architecture.

## [0.3.103] - 2026-08-18

### Fixed
- Dongle identity confirmation before BLE provisioning write (AUT-966): the app now lists every discovered dongle by name + MAC/remoteId and requires explicit user confirmation before it writes the WiFi SSID/PSK + one-time device API key. It writes only to the confirmed device — never the first BLE scan match, which a spoofed advertisement could previously hijack.

## [0.3.102] - 2026-08-18

### Changed
- Web favicon (AUT-1125): updated home-screen web app icons (`Icon-192.png` /
  `Icon-512.png`) and wired them into `frontend/web/index.html` so the hosted
  app shows the new AutoBrain branding as an installable Progressive Web App.

## [0.3.101] - 2026-08-18

### Fixed
- Hosted publish (AUT-1114): fixed Dart string-interpolation syntax error in
  the license screen subtitle (`'Managed by Stripe.}')` — unterminated string
  literal broke `flutter build web`, failing the image publish + manifest
  rotation so the `hosted` tag never advanced to 0.3.100.

## [0.3.100] - 2026-08-18

### Fixed
- Hosted worker/beat SECRET_KEY (AUT-996): added `SECRET_KEY` env var to the
  hosted `worker` and `beat` services in `docker-compose.hosted.yml`. Without
  this, Celery worker and beat processes could not sign/verify JWT tokens,
  causing task authentication failures on the hosted stack.

### Changed
- Hub registration keys wired into hosted compose (AUT-528): `docker-compose.hosted.yml` now passes `HUB_HOSTED_REGISTRATION_KEY` to the hub service (was missing — hub fails closed without it) and `SOCIAL_FEDERATION_HOSTED_REGISTRATION_KEY` to the backend so hosted servers present the registration key when registering with the hub. The repo compose reference now matches the live EP5 stack, which already had both vars set and the key rotated.

- App launcher icon (AUT-1106): updated mobile app icon for Android and iOS with fresh branding.

## [0.3.99] - 2026-08-18

### Added
- Knowledge graph tooling (AUT-1013): added graphify skill/agent for codebase
  analysis, queryable knowledge graph at `graphify-out/`, AST extraction, and
  cross-file relationship mapping. Supports `/graphify` command for efficient
  codebase navigation.

## [0.3.98] - 2026-08-18

### Fixed
- License screen (AUT-1004): when IAP is enabled but products aren't available for the current platform (e.g., store not yet published Play Console / App Store), the screen now falls back to Stripe checkout instead of showing a blank screen. Previously, if the server had IAP enabled but the store hadn't published products, the plans list was empty and users couldn't select upgrades. Now the screen shows Stripe-based upgrade plans as a fallback.


## [0.3.97] - 2026-08-17

### Fixed
- Alembic migration chain (AUT-1009): renumbered the duplicate `a1b2c3d4e5f6`
  revision in `add_devices` to `z2a3b4c5d6e7` and added `m3rge03` to merge the
  two remaining heads (`w5x6y7z8a9b0` + `z2a3b4c5d6e7`). `alembic upgrade head`
  now works at bootstrap instead of falling back to `create_all`. Added
  `test_alembic_revision_ids_unique` regression guard (from PR #187) to prevent
  future duplicate revision IDs.

## [0.3.96] - 2026-08-17

### Tests
- Alembic test guard (AUT-1009): new `test_alembic_revision_ids_unique` asserts every
  revision id is unique, catching the add_devices duplicate `a1b2c3d4e5f6` collision.
  Removed stray `a1b2c3d4e5f6_add_devices.bak` from migration versions.

## [0.3.95] - 2026-08-17

### Tests
- Backup regression net (AUT-1023): full-schema `serialize -> dump -> restore` roundtrip test now seeds one representative row per table across all 32 tables (community garage + market-data included) and every column storage class — guards against silent backup data loss or restore failure if schema/types drift again.

## [0.3.94] - 2026-08-17

### Fixed
- Dongle provisioning (AUT-969): when the dongle rejects a push with a token
  or window error, the app now explains the fix (re-pair and retry right after
  the pairing prompt) instead of echoing the firmware's terse
  "token missing or expired".
- Community Garage (AUT-992): duplicate `_report()` dropped the post-report
  path to the single AUT-896 `reportBuild` implementation — the leftover
  AUT-883 `flagBuild` copy was a merge duplicate that broke the mobile sync's
  analyze gate on main after PR #160 merged.

## [0.3.93] - 2026-08-17

### Fixed
- Community Garage (AUT-997): posts deleted by their author (or by an admin)
  no longer reappear in the feed after the next federation sync — a tombstone
  now records every removed build (local + remote) so the hub re-routing the
  post's event cannot resurrect it (mirrors the AUT-910 fix for remote
  copies).
- Dongle BLE provisioning token read: pass the timeout as int seconds to match
  `flutter_blue_plus` 1.32.8 `Characteristic.read()` (AUT-992). A `Duration`
  here broke the mobile sync's analyze gate on main.

### Security
- CI: weekly full-resolution dependency scan now also audits the `market-data`
  service tree (`.github/workflows/security-scan.yml` audits
  `backend`, `ai` and `market-data` requirements each in their own resolution);
  `rego-lookup-api` (a separate repo) now runs its own identical weekly scan.
  Previously only backend + AI trees were scheduled for CVE scanning, leaving
  the Playwright/Selenium and market-data transitive trees uncovered. The scan
  runs on `ubuntu-latest` (GitHub-hosted, live PyPI) because the self-hosted
  runner's pip index is a stale mirror that cannot resolve `uvicorn==0.34.0`,
  which would have failed the scan on every run.
- Market-data: the newly-enabled scan found `starlette 0.41.3` (via
  `fastapi==0.115.6`) in the market-data tree carrying the
  PYSEC-2026-161/248/249/1942/1941/2281/2280 CVE set. Bumped
  `market-data/requirements.txt` to `fastapi==0.133.0` +
  `starlette==1.3.1`, matching the backend/AI pins from AUT-794. Local
  `test_auth.py` + `test_scrape.py` pass against the bumped deps (AUT-1019).

## [0.3.92] - 2026-08-16

### Security
- Dongle provisioning (AUT-963): logout / server switch now clear the saved
  dongle credentials (WiFi password + one-time API key) so a previous
  account's device can never be re-provisioned from another account, and the
  app re-links the dongle when the saved device no longer belongs to the
  current account. SSID and WiFi password lengths are validated (1–32 /
  8–63 octets) before the BLE write.
- Dongle provisioning one-shot token (AUT-969): the app now reads a fresh
  random token from the dongle (characteristic 6E400004) and echoes it inside
  the provisioning payload, which the new firmware requires before accepting
  the WiFi/account config. Together with the firmware's LESC pairing and the
  120 s provisioning write window, a nearby BLE peer can no longer read or
  overwrite the WiFi password / device API key mid-setup (CWE-319 residual
  from the AUT-962 review).

### Fixed
- Dongle BLE provisioning ack (AUT-968): firmware now delivers the ack over a
  NOTIFY-enabled provisioning characteristic (firmware PR #4), and the app
  treats a completed BLE write as success when no ack arrives (older
  firmware) instead of timing out after 25 s and reporting a false failure.
  `err:already configured` reads as "already provisioned — factory-reset to
  re-push".
- Dongle WiFi input guards (AUT-968): SSID/password containing `"` or `\` are
  rejected up front (the dongle's substring parser cannot unescape them), and
  the SSID (32) / WPA2 passphrase (63) fields cap input at the firmware buffer
  sizes. A failed device-list load now shows a "could not reach the server"
  hint instead of silently showing "no dongle linked".

### Added
- Mobile dongle WiFi upload setup (AUT-936): Settings → Dongle WiFi upload
  enables the AutoBrain-Tripper's WiFi auto-upload, links the dongle to the
  account (one-time API key shown on create), picks a vehicle, and pushes the
  WiFi credentials over BLE to the dongle. Pairing requires the Bluetooth
  permission (declared for iOS + Android 12+). Backend + firmware landed in
  AUT-918.

## [0.3.91] - 2026-08-16

### Added
- Dongle WiFi trip auto-upload (AUT-918): per-device API key header auth,
  idempotent POST /devices/{id}/trips upload surface, and the diy_dongle
  logbook source. Offline-first firmware queue + BLE credential provisioning
  ship in autobrain-obd2-diy; mobile settings/BLE push is AUT-936.

## [0.3.90] - 2026-08-16

### Fixed
- Android licence/checkout: external payment and billing links now resolve on
  Android 11+ (manifest declares https/http VIEW intents) and fail with an
  actionable error that copies the link, instead of a silent "Could not open
  the link" (AUT-926).

## [0.3.89] - 2026-08-16

### Fixed
- Build edit PATCH now clears the caption when the client sends an explicit
  `null` (previously an explicit `null` was treated as "leave unchanged" and
  the caption stayed put) (AUT-903).
- Admin build takedown now deletes the build's photo rows instead of leaving
  them orphaned in the uploader's pool pointing at purged MinIO objects
  (AUT-889).
- Community Garage takedowns now propagate across the federation (AUT-902): deleting a
  locally-hosted build or Issues Blog post (by the author or an admin) tells the hub to
  drop the routed post and fan a `remove` event out, so the deleted post no longer
  lingers in the community hub on other servers. Servers also apply incoming `remove`
  events to their federated copies (builds and issue posts). The hub operator's
  "Remove post" action in the hub admin GUI does the same (hub repo, AUT-902).
- Community Garage admins can now remove any build post directly from the feed
  (community pages) — previously the delete button 404'd on posts they didn't author,
  and federated copies had no delete action at all (AUT-902).
- Security hardening: servers now ignore hub-relayed `remove` events for their own
  locally-hosted builds and issue posts — a takedown can only ever reach a federated
  copy, never the origin's local post. The federation hub also rejects `remove`
  produced through the generic event relay, closing a bypass of the origin check
  (AUT-907).
- Federated build copies that an admin removes from the feed now stay removed
  instead of resurrecting on the next federation sync: the removal is recorded as a
  tombstone and the inbox pull skips it, so a deleted copy does not reappear ~1 minute
  later (AUT-910).
- Admins can no longer delete Issues Blog posts hosted on another server — the
  admin delete endpoint now returns 403 for federated (origin="remote") posts;
  moderating an abusive remote post hides it locally via the existing hide action
  instead of deleting another server's copy (AUT-935).

### Added
- Report buttons on build posts and build comments — reports join the admin
  "To review" hub alongside issue reports; admins can delete reported builds
  and build comments (AUT-883).
- Dedicated "My Issues" tab next to Issues Blog showing your own issue blog
  posts (AUT-883).
- Build posts on the Community Garage hub feed can be reported ("Report post"
  in the build-detail menu). Reports are recorded locally and sent to the
  federation hub, where the operator sees them in a new Reported posts queue
  with the full post content, reason and reporter (AUT-896).
- Federation hub operator console: the Posts view now shows each post
  human-readably (title, author, make/model, caption, mod/photo counts) with
  text wrapping instead of raw JSON, and a Reported posts moderation list with
  Remove/Dismiss actions (AUT-896).

## [0.3.88] - 2026-08-16

### Fixed
- Community Garage edit-build screen: tapping the share-scope checkboxes
  (Photos / Vehicle specs / Mod list / Odometer / Notes) now toggles them. They
  previously appeared to do nothing because the picker mutated shared state
  without re-rendering (AUT-893).

## [0.3.87] - 2026-08-15

### Security
- Backend caps stored GPS samples per trip at 5000 (mirrors the client's 2400
  cap with headroom), bounding per-trip payload size on logbook create/update
  (AUT-852).

## [0.3.86] - 2026-08-15

### Added
- Issues Blog "My Issues" filter shows only your own posts (AUT-832).
- Report buttons on issue replies — reports go to a new admin "To review" hub
  alongside post reports (AUT-832).
- Admin moderation hub lists every flagged post/comment with the reporting
  reason and author; admins can delete the entry or ban/unban the author from
  posting in Community Garage (AUT-832).

## [0.3.85] - 2026-08-15

### Security
- market-data `POST /search` now checks the X-API-Key in constant time
  (`hmac.compare_digest`) and enforces per-IP and per-key rate limits, matching
  the rego-lookup-api and backend auth conventions (AUT-782).

## [0.3.84] - 2026-08-15

### Fixed
- Community Garage photo upload no longer crashes for photos whose MIME can't be
  detected (e.g. HEIC from the iOS camera roll): `image_picker` returns an empty
  string for `mimeType`, which used to blow up `MediaType.parse("")` and surface
  as "Could not save: … Invalid media type". The upload now sanitizes the content
  type (filename-derived MIME fallback, else `application/octet-stream`) and the
  photo pickers treat an empty MIME as missing, defaulting to `image/jpeg`
  (AUT-796, unblocks AUT-793).

## [0.3.83] - 2026-08-15

### Added
- Android Auto / car-kit trips now record their GPS route: position fixes are
  captured while a drive is active and saved to the logbook trip, so a drive
  logs a drawn path on the trip map (AUT-427).
- Logbook trip view now has an "Open in Google Maps" button that opens the
  trip's route drawn on Google Maps (AUT-427).

### Removed
- Generic ELM327 OBD2 adapter support removed (AUT-427): the app now supports
  only the custom-built OBD2 adapter. Bluetooth adapter connect/live-PID/VIN/
  DTC-from-adapter UI and the ELM327 protocol + BT-SPP transport layers were
  stripped. Trip start/stop comes from the phone-side car-kit / Android Auto
  path (AUT-367) with GPS route recording. The fault-code library + manual
  VIN entry remain.

## [0.3.82] - 2026-08-15

### Security
- `cryptography` bumped `44.0.1` → `50.0.0` to clear 7 known CVEs
  (PYSEC-2026-35/2141/3552/3553/3554, GHSA-537c-gmf6-5ccf) covering JWT
  signing, federation Ed25519 keys, and TLS/OpenSSL. CI now runs pip-audit on
  pinned backend + AI deps (AUT-781).
- Backend/AI: remediated transitive CVEs in the resolved dependency tree —
  bumped `fastapi` to 0.133.0 with `starlette` 1.3.1 (clears the starlette
  PYSEC-2026-161/248/249/1942/1941/2281/2280 set) and replaced the unmaintained
  `python-jose` (whose transitive `ecdsa` 0.19.2 carries PYSEC-2026-1325, with
  no patched release published) with `PyJWT[crypto]` (AUT-794).
- CI: added a weekly full-resolution dependency scan
  (`.github/workflows/security-scan.yml`) that audits the fully-resolved
  backend + AI tree — the PR-time `--no-deps` pip-audit gate cannot see
  transitive CVEs (AUT-794).

## [0.3.81] - 2026-08-15

### Fixed
- Community Garage photo uploads now accept iPhone/Android camera photos in
  HEIC/HEIF format: the backend decodes them (via pillow-heif) and stores the
  same compressed webp every other photo gets, so "photos still fail to upload"
  for default-format phone photos is resolved. Unsupported file types now show
  a clear "That photo can't be processed" message instead of a generic one
  (AUT-764).

## [0.3.80] - 2026-08-15

### Added
- Issues Blog posts now share across the federation like build posts do: a new
  help post is pushed to the hub and appears on other registered servers with
  its photos, and replies + resolved answers sync back (AUT-756).

### Fixed
- Unsharing a Community Garage build no longer returns HTTP 500 even when the
  build has a share scope (AUT-762). The AUT-703 fix (0.3.78) covered photos,
  comments and likes, but the per-build `social_share_scopes` row was still
  deleted through the ORM, which does not order child deletes before the parent
  delete (no `relationship()`/cascade), so Postgres rejected it with a
  `social_share_scopes_build_id_fkey` FK violation. The scope row is now
  bulk-deleted with the other child rows before the build. Regression test in
  `tests_social/test_social.py`.
- Photo uploads on the web app no longer fail silently ("nothing happens after
  I select the file"): the frontend CSP now allows same-origin `blob:` URLs
  that Flutter's image picker uses to preview/read picked images, and the
  compose screens surface a "Could not read that photo" message instead of
  dropping the selection silently (AUT-756).

## [0.3.79] - 2026-08-15

### Fixed
- The social federation server key no longer regenerates on every registration attempt (AUT-758). The Ed25519 keypair is now generated once and persisted in `social_server_config.hub_private_key`, so retrying a join reuses the same identity instead of rotating the key mid-join and failing. Regression test in `tests_social/test_social.py`.

## [0.3.78] - 2026-08-15

### Fixed
- Unsharing (deleting) a Community Garage build that had photos no longer returns HTTP 500 (AUT-703). The build delete ran the photo deletes through the ORM, which did not order the child deletes before the parent (no `relationship()`/cascade between `SocialBuild` and `SocialPhoto`), so Postgres rejected the delete with a `social_photos_build_id_fkey` FK violation. The photos are now bulk-released back to your unassigned uploads in the same way as dropping photos in Edit build, then the build is deleted. Regression test in `tests_social/test_social.py`.

## [0.3.77] - 2026-08-15

### Fixed
- Community Garage federation: the backend no longer claims `hub_status=registered` right after `POST /admin/social/register`. The hub's approval workflow (AUT-525) returns `status: pending` for new registrations, and the client now stores that state — a pending server stays local-only instead of silently failing every signed hub request with 401. Once the hub operator approves the server, the feed's federation sync polls the hub's public status endpoint and self-heals into `registered` (no manual re-register). The admin UI shows the pending state with a "Registration pending hub-operator approval" hint and a Refresh action. Regression tests in `tests_social/test_social.py` (AUT-731).

## [0.3.76] - 2026-08-15

### Added
- Issues Blog replies can now carry one photo each (AUT-736). The reply composer has an attach button (one photo, max), the photo uploads through the existing media pipeline on send, reply photos render inline on the post detail (tap to view full size), and they are cleaned up when the post is deleted.

## [0.3.75] - 2026-08-15

### Fixed
- License screen now distinguishes **License pending** (orange) from **Subscription active** (green): if a checkout was started but not paid (`incomplete` / `incomplete_expired` / `unpaid`) — or the account was granted but never actually paid for — the status shows "License pending" instead of implying the licence is active. `GET /auth/me` now reports a derived `license_status` (`active` / `pending` / `free`) so web + mobile agree, and never reports `active` without a paid entitlement.
- Users stuck with an unfinished/failed checkout (a pending Stripe subscription) can now retry paying — only sponsored accounts with no subscription record are blocked from buying a licence.

## [0.3.74] - 2026-08-15

### Fixed
- Hourly admin backup no longer fails on a transient DB blip during a deploy (AUT-696). `serialize_all` now retries (3 attempts, short backoff, session rollback) on transient `OperationalError`/`InterfaceError` (closed connection, DB restart mid-backup) before reporting failure to `autobrain-backup`, so a mid-deploy churn can't trip a backup alert. Regression test in `tests/test_backup_completeness.py`.

## [0.3.73] - 2026-08-14

### Added
- Issues Blog now lets you attach up to 4 photos to a post (AUT-709). Photos upload through the existing media pipeline, are rendered on the post detail + browse list, and are cleaned up when the post is deleted. A photo attached to an issue can no longer be claimed by a build (and vice-versa).

## [0.3.72] - 2026-08-14

### Fixed
- Alembic migration chain on `main` had two heads (`q1r2s3t4u5v6` from the Community Garage photo-position change and `u1v2w3x4y5z6` from the Issues Blog), which broke `alembic upgrade head` at bootstrap and forced the `create_all` fallback on every deploy. Added merge revision `m3rge02` re-unifying both branches (no-op upgrade body, same pattern as the earlier `m3rge01` merge) so `alembic heads` reports a single head and fresh/stamped databases migrate cleanly. Already-stamped databases (demo/default/hosted, AUT-682) apply it as a clean no-op. No schema or data changes.

## [0.3.71] - 2026-08-14

### Added
- Demo issues-blog content (AUT-712): the demo instance's Community Garage Issues Blog is seeded with 16 posts, each with 1–3 replies (~30 total), on next boot with `DEMO_RESET=true`. Answered/resolved posts pin their answer. Deterministic content (fixed tag vocabulary, `origin="demo"`, fictional replier names, staggered `created_at`) — no AI in the seed path. `reset_demo` now clears the demo user's posts/replies/flags before deleting the user (FK-safe on Postgres).


## [0.3.70] - 2026-08-14

### Fixed
- Community Garage feed no longer returns HTTP 500 when federation is registered with the hub (AUT-694). The hub answers an empty event pull with `next_cursor: 0`, and the first sync crashed on `int(0 or None)` → `TypeError` → every feed request 500'd until a cursor was stored. The cursor is now only stored when present (`next_cursor` + a `TypeError`/`ValueError` guard). The sync loop is also hardened so malformed hub payloads (non-dict builds/events, non-dict `snapshot`/`payload`) are skipped instead of crashing the feed. Regression tests in `tests_social/test_social.py`.

## [0.3.69] - 2026-08-14

### Fixed
- Community Garage share (AUT-676): the share dialog now has a **Copy link** button, and the shared link can be opened in-app so it renders on the user's own AutoBrain instance. Sharing a federated (remote-server) build no longer throws a raw error — it opens the build directly on the viewer's instance.

## [0.3.68] - 2026-08-14

### Added
- Community Garage **Issues Blog** frontend (AUT-627, AUT-644): third tab in Community Garage (Feed / My Builds / Issues Blog) with a blog-archive list (title, excerpt, author, tags, comment count, Open/Answered/Resolved status badge, date), keyword search + tag chips + status filter (server-side, deterministic), full blog-post detail with chronological comment thread, "Mark as answer" resolution flow with a resolved banner pointing at the pinned answer, "Report" moderation action, and a compose screen (title, body, optional vehicle context snapshot). Reuses Community Garage premium gating and "disabled by admin" states; wired to `/api/v1/social/issues`.
- Community Garage Issues Blog backend (AUT-627, AUT-643): `social_issue_posts` / `social_issue_comments` / `social_issue_flags` tables + Alembic migration, blog routes under `/api/v1/social/issues` (browse with tag/status/q filters and cursor pagination, create/edit/comment/mark-answer/flag/delete), admin moderation (`/api/v1/admin/issues/flagged`, hide/restore), deterministic fixed-vocabulary auto-tags, and global search integration for `issue` (community-visible, hidden posts excluded). Premium-gated, rate-limited, plaintext-only; no AI in authoring/answers/moderation.

### Fixed
- Issues Blog: editing your own post via PATCH `/api/v1/social/issues/{id}` no longer returns HTTP 500 (AUT-665). `updated_at` (`onupdate=func.now()`) was expired after commit and the async lazy load raised `MissingGreenlet`; `update_issue` now `refresh`es the post before serializing. Added a PATCH success-path regression test.

### Security
- Issues Blog rate limiting no longer trusts client-supplied `X-Forwarded-For` (AUT-670, F1): `client_ip()` keys on the proxy-set `X-Real-IP` / socket peer only, the nginx edge overwrites `X-Forwarded-For` with `$remote_addr`, and create/comment/answer now carry per-user caps (`social_user_rate_limit`) mirroring flags — so rotating the header can no longer reset the per-IP window. Regression suite `tests/test_pt1_xff_bypass.py`.
- Issues Blog answer pinning restricted to the post author (AUT-670, F2): a commenter can no longer pin their own comment and force the post to `resolved`; non-authors get 404 (PW-8 no-probing pattern). Author pinning still resolves the post.
- Issues Blog `cursor` pagination param capped at 512 chars (AUT-670, F3): oversized cursors are rejected with 422 by validation instead of being base64-decoded/parsed (mild parse DoS on attacker input); malformed short cursors still 400.

## [0.3.67] - 2026-08-14

### Added
- Community Garage photos per build raised from 6 to 15 (AUT-674): the compose picker (web + mobile) accepts up to 15 photos and the backend `POST /social/posts` validation caps `photo_ids` at 15 (was 12). Regression test asserts 15 IDs pass and 16 are rejected.

### Fixed
- Community Garage photo upload no longer rejects real phone photos (AUT-674): the social upload input gate was 5MB while receipts/fuel/logbook allow 15MB, and web + iOS multi-pick can't pre-downscale — typical modern phone photos (5–15MB) were returned `413 File too large`. Social uploads now use the same 15MB bounded-read cap as the rest of the app; the backend still downscales to 2048px and re-encodes to webp, so stored media stays small. Regression tests cover a >5MB accepted upload and the 413/415 gate.

## [0.3.66] - 2026-08-14

### Added
- Community Garage builds can now be named when sharing and fully edited afterwards (AUT-675): "Edit build" on My Builds lets you rename the project, change the caption, and reorder/add/remove photos, and it shows what the build shares (photos, specs, mods, odometer, notes) so you can edit that after the fact too. Photos keep their new order in the feed; dropped photos go back to your uploads. Backed by `POST/PATCH /social/posts` now accepting `title`, ordered `photo_ids` and `share_scope`, plus a new `social_photos.position` column.

## [0.3.65] - 2026-08-14

### Fixed
- Celery worker/beat healthcheck (AUT-601): the `autobrain-worker` image healthcheck is now command-aware. The beat scheduler container (which shares the image) previously ran `celery inspect ping` — a check that only a *worker* can answer, so it reported health for the wrong process. It now verifies the `celerybeat-schedule` file exists and stays fresh (missing or stale file flags the wedged scheduler busy-loop behind the 100% CPU incident). The worker check pings only its own node (`-d celery@$(hostname)`) so the backend's embedded worker on the same broker can't stall it, and gets an 8s reply window inside a 15s healthcheck timeout so AI-task load no longer false-negatives it.

## [0.3.64] - 2026-08-14

### Fixed
- Social upload bounded-read overflow (AUT-660): `read_upload` now runs inside the `MediaError` handler, so a >5MB chunked/misdeclared `Content-Length` body returns `415` as documented instead of an unhandled `500`.

## [0.3.63] - 2026-08-14

### Fixed
- `#/license` deep-link race (AUT-629): the Flutter web engine cleared the URL fragment via `history.replaceState` before the logged-in session-restore rebuild, so fresh loads of `/#/license` landed on Home. The fragment is now captured once in `main()` before `runApp` and routing reads the captured value, restoring reliable deep-link navigation to the License screen.

## [0.3.62] - 2026-08-14

### Fixed
- PR run failures (AUT-633): the changelog gate now diffs against the merge-base instead of the live base-branch tip, so a stale PR no longer false-fails (or slips a missing CHANGELOG.md entry when main happened to move one). The mobile sync workflow also rebases onto remote main before pushing, so concurrent sync runs stop reddening with `fetch first` rejections.

## [0.3.61] - 2026-08-14

### Added
- Backend store-native IAP (AUT-617): Apple App Store / Google Play receipt verification for the mobile store builds — `GET /billing/iap/catalog`, `POST /billing/iap/verify`, and `POST /billing/iap/webhook/{apple,google}`. Purchases are recorded server-side and durable; active store entitlements grant the same plans as Stripe (`plan_for_user` + `GET /auth/me` now surface `iap_status`). Renewals/refunds propagate via verify-on-refresh on `/auth/me` plus the store webhooks once the store teams configure them.

### Security
- Backend IAP hardening (AUT-622 review on AUT-617): App Store webhook certificate-chain verification now validates the terminal cert against Apple's root by key, not subject string (forged-root spoof closed); Play purchases are replay-protected (one store purchase grants at most one account, enforced by unique DB constraints + ownership check); Google subscriptions settle to `expired`/`revoked` on definitive non-active state; per-user verify/refresh cooldown + rate limit bound external store calls; Google Pub/Sub push JWKS cached with issuer/expiry checks.
- Backend IAP webhook crash hardening (AUT-625 re-review on AUT-617): invalid-signature chain forgery on `POST /billing/iap/webhook/apple` now returns a clean 400 instead of an unhandled HTTP 500 (`InvalidSignature` caught in `_chain_verified`/`_verify_apple_signed_payload`); regression test forges the root with Apple's full subject.
- Backend IAP QA follow-ups (AUT-628): first-time iOS verify of an already-expired transaction now rejects with the entitlement settling to `expired` instead of reporting `active`; added regression tests for the verify rate-limit 429 branch, Apple webhook bundle-id mismatch, empty `signedTransactionInfo` skip, and iOS refresh demotion on non-active store status. Documented that the process-local verify rate limiter is invalidated if the backend scales to multiple workers (N4).

## [0.3.60] - 2026-08-14

### Fixed
- Full-DB backups now cover every table (AUT-521): the snapshot table list is derived from the ORM metadata instead of a hand-maintained list that had drifted — `market_listing_cache` and `revoked_refresh_tokens` were missing entirely, and `vehicle_shares` was only added on 2026-08-10. A backup taken before a table was added, when restored by newer code, wiped that table's rows without re-inserting them — the mechanism that could silently remove shared vehicles during a server upgrade/restore. `serialize_all`/`restore_all` now use SQLAlchemy's FK-aware table order, and a regression test asserts the snapshot covers the full schema and that a backup/restore roundtrip preserves shared vehicles.
- Demo reset no longer orphans (or crashes on) shared vehicles (AUT-521): `reset_demo` deleted the demo user + vehicles without clearing `vehicle_shares` first, so a share referencing a demo vehicle or the demo account either left orphaned rows (FK-less DBs) or blocked the deletes on Postgres (`NO ACTION`) and crashed the boot. It now deletes those shares before the user/vehicles, with a regression test covering both directions (demo as share owner and as invitee).

## [0.3.59] - 2026-08-14

### Fixed
- Community Garage "My Builds" tab now matches the feed's 12px card spacing (AUT-614): `my_builds_screen.dart` switched from `ListView.builder` to `ListView.separated` with a `SizedBox(height: 12)` separator, mirroring `social_screen.dart`.

## [0.3.58] - 2026-08-14

### Fixed
- Worker log calls no longer crash with `TypeError` on structlog-style `key=` kwargs (AUT-603): `tasks.py` used stdlib `logging.getLogger` but passed kwarg events, so `scheduled_backup` stored its snapshot then failed on the success log line. Switched to the codebase structlog `get_logger`.

## [0.3.57] - 2026-08-13

### Fixed
- Worker daily `scheduled_backup` now stores in-stack MinIO snapshots (AUT-583): local `async def _run()` shadowed the module `_run(coro)` helper, raising `TypeError` so the daily task never wrote `backups/autobrain-backup-*.json`. Renamed to `_do()` with regression tests in `backend/tests/test_workers.py`.
- Restored the Celery worker image to CI (AUT-583): `docker/worker/Dockerfile` + `worker` added to the `dockerhub-publish` and `build-hosted` image loops, so `autobrain-worker` picks up worker fixes on every merge (it had no build path since the P1-1 consolidation).

## [0.3.56] - 2026-08-13

### Fixed
- Social uploads no longer buffer the full request body before size validation (AUT-597): `POST /api/v1/social/uploads` rejects oversize `Content-Length` with 413 before reading, and a bounded read loop aborts with 415 once buffered bytes exceed the 5MB cap.

## [0.3.55] - 2026-08-13

### Fixed
- Billing hardening for the AUD currency migration (AUT-523 security follow-ups): `_apply_subscription` no longer demotes an actively-billed subscriber whose Stripe price was archived/rotated (grandfathered pre-AUD prices keep their plan until the subscription lapses), and `scripts/stripe-setup.py` refuses to archive a price that active subscriptions still reference (plus an `assert` hardened to an explicit `sys.exit`).

## [0.3.54] - 2026-08-13
### Added
- Demo Community Garage builds now each ship with 3 photos (AUT-529): every demo build shows media in the feed instead of only the first build having a single image. Existing demo instances pick this up on next `DEMO_RESET` restart.

## [0.3.53] - 2026-08-13

### Added
- Community Garage feed search (AUT-530): search bar on the Feed tab (debounced 350ms, server-side `?q=`) filters posts by title, caption, author and server name, with a clear button and a search-aware empty state. Feed cards are now separated by 12px spacing (`ListView.separated`).

## [0.3.52] - 2026-08-13

### Added
- License opens an external browser tab on store-published mobile builds (AUT-531): the mobile License button launches the web License screen at `https://<api-origin>/#/license` in the OS browser, and the web app deep-links `/#/license` straight to the License screen. Avoids in-app purchase billing for app-store subscriptions (Apple/Google 30% IAP).

## [0.3.51] - 2026-08-13

### Fixed
- GitHub Actions "run failed" noise (AUT-540): the publish workflow only auto-cuts releases when the ref is `main` (a `workflow_dispatch` on a feature branch no longer tries to push to `main` and fail), git identity is set before the auto-bump push/rebase retry, and the changelog gate is skipped for `dependabot[bot]` PRs (they never modify CHANGELOG.md).

## [0.3.50] - 2026-08-13

### Fixed
- Logbook GPS button on mobile (AUT-539): the "Use GPS" icon always showed "GPS unavailable" because the native (non-web) helper `frontend/lib/core/geoloc_io.dart` was a hard-coded `null`. It now uses the `geolocator` plugin: checks location services, requests permission on first use, and stamps the current `lat, lng` (10s fix timeout) into the trip start/end location. iOS: added `NSLocationWhenInUseUsageDescription`. Android permissions (`ACCESS_FINE/COARSE_LOCATION`) were already declared for the car-kit GPS path.

## [0.3.49] - 2026-08-13

### Fixed
- Community Garage federation registration on AutoBrain-Hosted (AUT-532): registering the server with the hub (`POST /admin/social/register`) returned 502 "Hub unreachable: hub not configured" because no compose file passed `SOCIAL_FEDERATION_HUB_URL` to the backend. All three compose files now wire the hub URL (default `https://hub.autobrainservice.app`) and the hosted stack registers `hosted=true` (free bundled license, per docs R5a). A regression test guards the compose wiring.

## [0.3.48] - 2026-08-13
### Fixed
- Subscription billing is now in **AUD** (AUT-523): `/billing/pricing` returns `currency: aud`, the license screen renders `A$` prices, and `scripts/stripe-setup.py` provisions/verifies Stripe prices in AUD (archiving the old USD prices). Stripe `STRIPE_PRICE_*` env values must be refreshed from a re-run of the script before checkout goes live.

## [0.3.47] - 2026-08-13

### Security
- Federation hub registration: `register()` now sends `registration_key` (from `SOCIAL_FEDERATION_HOSTED_REGISTRATION_KEY`, a deploy-time secret) whenever a server presents itself as `hosted=true`. Self-hosted servers send an empty key and register unlicensed as before. Closes the hosted=true free-license bypass on the hub (AUT-525).

## [0.3.46] - 2026-08-13

### Removed
- Server version check removed entirely (AUT-461): the GitHub update check (`/api/v1/version/mobile`, the GitHub portion of `/admin/version`, and `backend/app/services/version.py`) is gone. The server no longer touches the GitHub API at all — no PAT, no anonymous rate-limit usage. `/admin/version` still returns the local server version string; the admin UI shows it without any update banner. The mobile app's release banner now uses only the release advertised by its server (`/auth/config app_version`).

## [0.3.45] - 2026-08-13

### Fixed
- Mobile release builds failing on `AuthState` (AUT-522): the mobile-only `auth_state.dart` delta in `CannonFodder151/autobrain-mobile` had drifted from this web base and was missing the `freeAccount`/`premium` getters the synced Community Garage screens use, so every mobile release since v0.3.34+69 failed to compile. The mobile delta was re-merged onto the web base (getters + refresh-token flow restored) and a `flutter analyze` CI guard was added to `autobrain-mobile` so a stale delta can never silently break a release again.

## [0.3.44] - 2026-08-13

### Fixed
- Alembic migration chain unbroken for create_all-hybrid DBs (AUT-510): the social-tables migration `n4p5q6r7s8t9` is reparented onto the logbook head so the chain has a single head again (`alembic upgrade head` no longer fails with "Multiple head revisions"), and every DDL op in the social migrations is guarded to skip already-present tables/columns. Boot on all tiers converges to the schema head automatically; no manual `ALTER TABLE` needed anymore.

## [0.3.43] - 2026-08-13

### Fixed
- Community Garage no longer shows the "Community Garage" title twice (AUT-511): the Feed tab dropped its own app bar since the parent screen already shows the title.

## [0.3.42] - 2026-08-13

### Changed
- Community Garage admin Settings moved out of the tab bar into the AppBar 3-dot menu (AUT-502) so it no longer takes up the whole screen; non-admins see no menu.

## [0.3.41] - 2026-08-13

### Added
- My Builds tab in the Community Garage (AUT-501): view and edit your own posts. Backed by `GET /social/my-posts` + `PATCH /social/posts/{id}`.


## [0.3.40] - 2026-08-13

### Security
- Hosted stack port lockdown (AUT-473): the 9Router admin dashboard + OpenAI-compatible API (`:20128`) and the app origin (`:8086`) are now bound to `127.0.0.1` only on AutoBrain-Hosted. Backend/ai reach 9Router over docker DNS (`http://9router:20128/v1`), and all client traffic is forced through Cloudflare; no plaintext origin bypass remains. Data persists on the external `9router-data` volume. See `docs/deployment-guide.md` (security/lockdown section + redeploy rules).

## [0.3.39] - 2026-08-13

### Changed
- Community Garage moved from the app-bar menu to a home-screen feature tile button (AUT-488), matching the Fuel/Logbook style; Settings & security stays in the menu.

## [0.3.38] - 2026-08-13

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
- Community Garage hardening (AUT-462): per-IP rate limits on social routes (429 + `Retry-After`), 5MB upload cap with 2048px downscale, 15-minute presigned URL TTL, non-owner delete returns 404, signed `X-Nonce` federation replay protection, and like/comment fan-out to remote copies with author/server/caption preservation.
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
