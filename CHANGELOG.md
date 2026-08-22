# Changelog

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/).

> This is the single shared changelog for BOTH the hosted (web) app (`frontend/`)
> and the mobile app (`CannonFodder151/autobrain-mobile`). Every feature or
> user-facing change ships with an entry here under `[Unreleased]` — see
> `CONTRIBUTING.md` for the frontend-parity + changelog rules.




## [Unreleased]

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
