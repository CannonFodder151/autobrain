# AUT-1187 — Backend security hardening (5 findings)

Fixes all 5 security findings from the backend audit. QA + Security sign-off requested.

## AB-06 — Global per-IP rate limiting (MEDIUM)
New `RateLimitMiddleware` (`backend/app/middleware/rate_limit.py`):
- Redis fixed-window counters, keyed `ip:method:path:window`
- Default **60 req/min**; overrides: signup **5/min**, password-reset **3/min**, login/MFA **10/min**
- Fail-open on Redis outage (logged) so a broker blip can't take down the API
- Adds `X-RateLimit-Limit/Remaining/Reset` headers; 429 carries `Retry-After`
- OPTIONS preflight + `/health` skipped

## AB-07 — ILIKE wildcard abuse (MEDIUM)
- `_escape_ilike()` escapes `\`, `%`, `_`; applied with `escape="\\"` in both
  `admin.py` and `admin_api.py` user search
- `admin-api /users` now paginated (`page`, 15/page)

## AB-09 — Backup restore integrity (MEDIUM)
- `dump_backup()` appends SHA-256 checksum of canonical JSON
- `load_backup()` validates schema version + required fields + checksum via `hmac.compare_digest`
- `restore_all()` wrapped in `db.begin()` transaction — mid-restore failure leaves DB unchanged

## AB-14 — Asset restore OOM (MEDIUM)
- Upload streamed to temp file in 1 MB chunks, **1 GB cap** (was 5 GB fully in RAM)
- New `restore_assets_file()` streams tar members to MinIO without loading archive into memory

## AB-10 — Signup user enumeration (LOW)
- `POST /auth/signup` returns identical response for existing/new email and display-name collision
- Setup email sent only for genuinely new accounts

## Verification
Assert-based self-check passed: escape function, checksum tamper rejection,
missing-checksum rejection, wrong-version rejection, unsafe tar member rejection,
route-limit matching, uniform signup shape.

## Test plan
- [ ] QA: signup twice with same email → identical responses
- [ ] QA: 6 signups/min from one IP → 429 on 6th
- [ ] Security: tampered backup file rejected at load
- [ ] Security: `%`/`_` in admin search returns literal matches only
