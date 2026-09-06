# Integrating AutoBrain with Other Software

A human-readable guide for platforms, services and tools that want to talk to
AutoBrain. It covers the **global API** — the endpoints almost every integrator
needs: authentication, and creating, reading, updating and removing user
accounts. Vehicle-level APIs (logbook, fuel, services, diagnostics, OBD, mods,
valuation…) are listed in [api-spec.md](api-spec.md) and share the same auth.

Every "GET and SET" endpoint below has a worked example.

## 1. The basics

| Thing | Value |
|-------|-------|
| Base URL | `https://hosted.autobrainservice.app/api/v1` |
| Format | JSON over HTTPS (always HTTPS — never plain HTTP) |
| API key | `X-Admin-API-Key: <ADMIN_API_KEY>` (server administrator provides it) |
| User token | `Authorization: Bearer <access_token>` (obtained from `/auth/login`) |

The hosted instance listens at `hosted.autobrainservice.app`. Self-hosted
installations use their own `APP_BASE_URL`, so swap the host in every example.

### Two ways to authenticate

1. **As a user** — a `Bearer` JWT from `/auth/login`. Use this for anything a
   real person could do (read/write their vehicles, logbook, etc.).
2. **As an integrator (machine-to-machine)** — a single shared API key in the
   `X-Admin-API-Key` header. Use this for account provisioning, permissions and
   backups. This is the path most integrations want.

### Quickstart (4 steps)

```bash
# 1. Check the server is up
curl https://hosted.autobrainservice.app/health

# 2. Log in as a user to get a token
curl -s -X POST https://hosted.autobrainservice.app/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@autobrainservice.app","password":"demo"}'

# 3. Call an authenticated endpoint with that token
curl -s https://hosted.autobrainservice.app/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"

# 4. Provision a user machine-to-machine (admin API key)
curl -s -X POST https://hosted.autobrainservice.app/api/v1/admin-api/users \
  -H "X-Admin-API-Key: <ADMIN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"email":"driver@partner.app","display_name":"Sam Driver","password":"CorrectHorseBattery"}'
```

## 2. Authentication (as a user)

### 2.1 `GET /auth/config` — is signup even open?

Public, no auth. Frontend clients call this to decide whether to show the
signup button and whether MFA is forced.

```bash
curl https://hosted.autobrainservice.app/api/v1/auth/config
```

```json
{
  "signup_enabled": true,
  "mfa_enforced": true,
  "license_enabled": true,
  "app_version": "1.4.2"
}
```

### 2.2 `POST /auth/login` — get a token pair

Sets: email + password in, tokens out.

```bash
curl -s -X POST https://hosted.autobrainservice.app/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@autobrainservice.app","password":"demo"}'
```

When the account has no MFA, you get a token pair with the user object:

```json
{
  "token_pair": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "user": {
      "id": "9f2c1a4e-8b3d-4d6f-a1c2-5e7d8f9a0b1c",
      "email": "demo@autobrainservice.app",
      "display_name": "Demo",
      "role": "demo",
      "is_active": true,
      "mfa_enabled": false,
      "max_vehicles": 3,
      "free_account": false,
      "obd_enabled": true,
      "obd_auto_connect": false
    }
  },
  "mfa_required": false,
  "mfa_setup_required": false,
  "mfa_token": null
}
```

Two special cases (account has MFA, or MFA is enforced and not yet set up):

```json
{
  "token_pair": null,
  "mfa_required": true,
  "mfa_setup_required": false,
  "mfa_token": "<mfa_session_token>"
}
```

```json
{
  "token_pair": null,
  "mfa_required": false,
  "mfa_setup_required": true,
  "mfa_token": "<mfa_session_token>"
}
```

In either case the login is **not complete**. Complete it by sending the 6-digit
TOTP code back:

```bash
curl -s -X POST https://hosted.autobrainservice.app/api/v1/auth/mfa/verify \
  -H "Content-Type: application/json" \
  -d '{"mfa_token":"<mfa_session_token>","code":"123456"}'
```

The response is a fresh token pair (`access_token`, `refresh_token`,
`token_type`, `user`). Wrong password or wrong code → `401`.

### 2.3 `POST /auth/refresh` — keep a session alive

Sets: a refresh token in, a new pair out. Refresh tokens rotate on every use —
the presented one is revoked immediately, so never send an old one twice.

```bash
curl -s -X POST https://hosted.autobrainservice.app/api/v1/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": { "id": "9f2c1a4e-...", "email": "demo@autobrainservice.app", "role": "demo" }
}
```

### 2.4 `GET /auth/me` — who am I?

The authenticated user's profile plus plan/quota numbers (the current
access token is sent automatically via the `Authorization` header).

```bash
curl https://hosted.autobrainservice.app/api/v1/auth/me \
  -H "Authorization: Bearer <access_token>"
```

```json
{
  "id": "9f2c1a4e-8b3d-4d6f-a1c2-5e7d8f9a0b1c",
  "email": "demo@autobrainservice.app",
  "display_name": "Demo",
  "role": "demo",
  "is_active": true,
  "mfa_enabled": false,
  "max_vehicles": 3,
  "free_account": false,
  "obd_enabled": true,
  "obd_auto_connect": false,
  "vehicle_count": 2,
  "vehicles_remaining": 1,
  "plan": "enthusiast",
  "subscription_status": "active"
}
```

### 2.5 `PATCH /auth/settings` — self-service toggles (user)

Users may only toggle `obd_auto_connect`; tier and OBD *access* are
admin-managed. Unrecognised fields are silently ignored.

```bash
curl -s -X PATCH https://hosted.autobrainservice.app/api/v1/auth/settings \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"obd_auto_connect": true}'
```

Returns the updated `UserOut` object (same shape as in `2.4`).

### 2.6 `POST /auth/logout` — revoke every session

Sets: a refresh token in, all outstanding tokens for that account invalidated
out. Logs the account out everywhere (including stolen tokens).

```bash
curl -s -X POST https://hosted.autobrainservice.app/api/v1/auth/logout \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"<refresh_token>"}'
```

```json
{ "message": "Logged out — all sessions were revoked" }
```

## 3. Creating & managing users — Admin API (machine-to-machine)

Authenticated with the `X-Admin-API-Key` header. Ask the server administrator
for the key. If `ADMIN_API_KEY` is empty the whole `/admin-api` prefix is
disabled.

### 3.1 `GET /admin-api/users` — list users

Gets all users, newest first. Optional `?q=` searches display name or email
(case-insensitive, partial match).

```bash
curl -s "https://hosted.autobrainservice.app/api/v1/admin-api/users?q=demo" \
  -H "X-Admin-API-Key: <ADMIN_API_KEY>"
```

```json
[
  {
    "id": "9f2c1a4e-8b3d-4d6f-a1c2-5e7d8f9a0b1c",
    "email": "demo@autobrainservice.app",
    "display_name": "Demo",
    "role": "demo",
    "is_active": true,
    "mfa_enabled": false,
    "max_vehicles": 3,
    "free_account": false,
    "obd_enabled": true,
    "obd_auto_connect": false,
    "created_at": "2026-01-15T09:30:00Z",
    "pending": false
  }
]
```

### 3.2 `POST /admin-api/users` — create a user

Sets: a new account. Two ways to provision:

- **Password now** (`send_invite` unset): the user can log in immediately.
- **Email invite** (`send_invite: true`): AutoBrain emails them a 7-day setup
  link to pick a password + MFA.

```bash
curl -s -X POST https://hosted.autobrainservice.app/api/v1/admin-api/users \
  -H "X-Admin-API-Key: <ADMIN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "email": "driver@partner.app",
    "display_name": "Sam Driver",
    "password": "CorrectHorseBattery",
    "role": "user",
    "max_vehicles": 2,
    "send_invite": false,
    "free_account": true,
    "obd_enabled": false
  }'
```

Success (`201`) returns the created user:

```json
{
  "id": "7a91d2f3-4b5c-4d6e-8f9a-1b2c3d4e5f60",
  "email": "driver@partner.app",
  "display_name": "Sam Driver",
  "role": "user",
  "is_active": true,
  "mfa_enabled": false,
  "max_vehicles": 2,
  "free_account": true,
  "obd_enabled": false,
  "obd_auto_connect": false,
  "created_at": "2026-08-12T14:00:00Z",
  "pending": false
}
```

Failures:

| Status | Meaning |
|--------|---------|
| `409` | `Email already registered` |
| `422` | Password missing **and** invite off (`Password required (or enable email invite)`) |

### 3.3 `PATCH /admin-api/users/{user_id}` — update permissions

Sets: any of `display_name`, `role`, `is_active`, `password`, `max_vehicles`,
`free_account`, `obd_enabled`, `obd_auto_connect`. Send **only** the fields you
want to change. Changing `password` revokes every outstanding token for that
user (they must log in again).

```bash
curl -s -X PATCH https://hosted.autobrainservice.app/api/v1/admin-api/users/7a91d2f3-4b5c-4d6e-8f9a-1b2c3d4e5f60 \
  -H "X-Admin-API-Key: <ADMIN_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"role":"user","max_vehicles":5,"free_account":false}'
```

```json
{
  "id": "7a91d2f3-4b5c-4d6e-8f9a-1b2c3d4e5f60",
  "email": "driver@partner.app",
  "display_name": "Sam Driver",
  "role": "user",
  "is_active": true,
  "mfa_enabled": false,
  "max_vehicles": 5,
  "free_account": false,
  "obd_enabled": false,
  "obd_auto_connect": false,
  "created_at": "2026-08-12T14:00:00Z",
  "pending": false
}
```

Unknown user id → `404 { "detail": "User not found" }`.

### 3.4 `POST /admin-api/users/{user_id}/disable` — suspend an account

Sets: `is_active` to false. The user can no longer log in or refresh, but their
data is preserved.

```bash
curl -s -X POST https://hosted.autobrainservice.app/api/v1/admin-api/users/7a91d2f3-4b5c-4d6e-8f9a-1b2c3d4e5f60/disable \
  -H "X-Admin-API-Key: <ADMIN_API_KEY>"
```

```json
{
  "id": "7a91d2f3-4b5c-4d6e-8f9a-1b2c3d4e5f60",
  "email": "driver@partner.app",
  "display_name": "Sam Driver",
  "role": "user",
  "is_active": false,
  "mfa_enabled": false,
  "max_vehicles": 5,
  "free_account": false,
  "obd_enabled": false,
  "obd_auto_connect": false,
  "created_at": "2026-08-12T14:00:00Z",
  "pending": false
}
```

### 3.5 `DELETE /admin-api/users/{user_id}` — remove a user (and their data)

Deletes the account and all of its data (vehicles, records, assets). There is
no undo. The last admin on the server can never be deleted.

```bash
curl -s -X DELETE https://hosted.autobrainservice.app/api/v1/admin-api/users/7a91d2f3-4b5c-4d6e-8f9a-1b2c3d4e5f60 \
  -H "X-Admin-API-Key: <ADMIN_API_KEY>"
```

Success → `204` with no body.

### 3.6 `GET /admin-api/backup` — full database snapshot

Downloads the entire database as a JSON file (`autobrain-backup-YYYYMMDD-HHMMSS.json`)
for off-box retention. There is also `POST /admin-api/restore` (upload the
snapshot to wipe and restore) — only automate that after reading the restore
warnings in [backup-strategy.md](backup-strategy.md).

```bash
curl -s https://hosted.autobrainservice.app/api/v1/admin-api/backup \
  -H "X-Admin-API-Key: <ADMIN_API_KEY>" -o autobrain-backup.json
```

## 4. User management over the admin web API (Bearer token)

The admin web app does the same operations, but authenticates as an admin user
(`role: "admin"`). Same payloads and semantics as Section 3, with two extras:
`/admin/users/{id}/backup` and `/admin/users/{id}/restore` for per-user
portability. Use the Admin API (Section 3) for server-to-server integration.

| Method | Path | Notes |
|--------|------|-------|
| GET | `/admin/users?q=&page=` | Paginated list, 15 per page: `{items, total, page, pages}` |
| POST | `/admin/users` | Same body as `3.2`; also rejects duplicate display names (`409`) |
| PATCH | `/admin/users/{id}` | Same body as `3.3` |
| POST | `/admin/users/{id}/re-upgrade?enabled=true` | Grant/revoke paid-tier benefits without Stripe |
| DELETE | `/admin/users/{id}` | Refuses to delete your own account |
| GET | `/admin/users/{id}/backup` | Download one user's profile JSON |
| POST | `/admin/users/{id}/restore` | Restore/override one user from a profile export |

```bash
curl -s "https://hosted.autobrainservice.app/api/v1/admin/users?q=sam&page=1" \
  -H "Authorization: Bearer <admin_access_token>"
```

```json
{
  "items": [
    {
      "id": "7a91d2f3-4b5c-4d6e-8f9a-1b2c3d4e5f60",
      "email": "driver@partner.app",
      "display_name": "Sam Driver",
      "role": "user",
      "is_active": true,
      "mfa_enabled": false,
      "max_vehicles": 2,
      "free_account": true,
      "obd_enabled": false,
      "obd_auto_connect": false,
      "created_at": "2026-08-12T14:00:00Z",
      "pending": false
    }
  ],
  "total": 1,
  "page": 1,
  "pages": 1
}
```

## 5. Field reference

### User create body (`POST /admin-api/users`, `POST /admin/users`, `POST /auth/register`)

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `email` | string | yes | — | Stored lowercased; must be unique |
| `display_name` | string | yes | — | 1–120 chars; must be unique (case-insensitive) |
| `password` | string | no | — | 8–128 chars; required unless `send_invite` is on |
| `role` | string | no | `user` | `admin` or `user` |
| `max_vehicles` | int | no | `1` | 1–1000 |
| `send_invite` | bool | no | `false` | Email a 7-day setup link instead of a password |
| `free_account` | bool | no | `false` | `true` disables AI features + rego lookup for the user |
| `obd_enabled` | bool | no | `false` | Grant OBD-II access |

### User update body (`PATCH /admin-api/users/{id}`, `PATCH /admin/users/{id}`)

Any subset of: `display_name`, `role` (`admin`/`user`), `is_active`,
`password` (8–128, revokes sessions), `max_vehicles` (1–1000),
`free_account`, `obd_enabled`, `obd_auto_connect`.

### User object (every read returns this shape)

| Field | Type | Notes |
|-------|------|-------|
| `id` | string (UUID) | Use this as `{user_id}` in paths |
| `email` | string | |
| `display_name` | string | |
| `role` | string | `admin` / `user` / `demo` |
| `is_active` | bool | `false` = suspended |
| `mfa_enabled` | bool | |
| `max_vehicles` | int | Vehicle quota |
| `free_account` | bool | `true` = AI/rego disabled |
| `obd_enabled` | bool | |
| `obd_auto_connect` | bool | |
| `created_at` | ISO-8601 | |
| `pending` | bool | `true` = invited, hasn't set a password yet |

## 6. Errors & limits

- **Error body** — every failure returns a JSON `{"detail": "<message>"}`.
- **`401`** — bad credentials, expired/malformed token.
- **`403`** — account disabled, role not allowed, or feature disabled for the
  plan (e.g. AI/rego on a free account).
- **`404`** — unknown resource (user id, vehicle id, etc.).
- **`409`** — duplicate email or display name.
- **`422`** — validation failure (missing field, bad value, out-of-range).
- **`429`** — too many requests. Login is rate-limited per IP.
- **MFA** — if the server enforces MFA, new accounts must complete MFA setup
  before login returns tokens (see `2.2`).

## 7. Security notes

- Always use HTTPS; the bearer and admin tokens are full-account credentials.
- The admin API key is the master key for the account database — keep it in a
  secrets manager, rotate it regularly, and never put it in client code.
- Deleting a user removes their data permanently — offer a disable + retention
  window (`3.4`) before hard delete (`3.5`) in any integration workflow.
- Setting a password via PATCH revokes the user's existing sessions; expect
  their app to force a re-login.
