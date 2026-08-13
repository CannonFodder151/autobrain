# Integrating AutoBrain with other software

A human-readable guide for connecting an external platform, CRM, admin portal or
automation to the **AutoBrain global API** — creating, reading, updating and
deleting user accounts, plus signing in as a user.

This document mirrors the machine-readable spec that every server generates.
Every server ships an interactive **Swagger UI** and a raw **OpenAPI** document;
the examples here come straight from that spec:

| Reference | URL (replace `YOUR-SERVER` with your host) |
|-----------|---------------------------------------------|
| Swagger UI (interactive — try the endpoints in the browser) | `https://YOUR-SERVER/docs` |
| OpenAPI JSON (machine-readable spec) | `https://YOUR-SERVER/openapi.json` |
| Hosted AutoBrain API | `https://hosted.autobrainservice.app/api/v1` |

All endpoints below are under the `/api/v1` prefix unless noted. Everything is
JSON. Set `Content-Type: application/json` on any request that carries a body.

---

## 1. Two ways in

AutoBrain has two API surfaces. Pick the one that matches your use case.

| Surface | Auth | Who it is for | Example calls |
|---------|------|---------------|---------------|
| **User API** | `Authorization: Bearer <access_token>` | Acting *as* a user (the mobile/web app, or a logged-in integration) | `POST /auth/login`, `GET /auth/me` |
| **Admin API** | `X-Admin-API-Key: <key>` | Machine-to-machine user administration (CRM sync, onboarding automation, backup agents) | `POST /admin-api/users`, `GET /admin-api/users` |

The Admin API uses one shared key configured by the server operator
(`ADMIN_API_KEY`). If that key is not set on the server, every `/admin-api/*`
call returns `403`. The `/admin/users/*` routes offer the same operations
authenticated as a logged-in user with the `admin` role (Bearer token) — see
section 5.

> Demo accounts are read-only, and every AI/rego feature is disabled for
> `free_account: true` users. Plan/feature entitlement is enforced server-side.

---

## 2. Signing in (getting a user token)

### `POST /auth/login`

Authenticates an existing account. On success you receive a token pair. On the
hosted instance **MFA is enforced**, so read the response shape carefully:

- **No MFA** → `token_pair` is populated. Use `access_token` immediately.
- **MFA required** → `mfa_required: true` plus an `mfa_token`. You must call
  `POST /auth/mfa/verify` with a TOTP code to obtain the real token pair.
- **MFA setup required** (first login, enforced MFA) → `mfa_setup_required: true`
  plus an `mfa_token`; enrol the user via `/auth/mfa/setup-session` then
  `/auth/mfa/complete-setup`.

**Request**

```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "email": "jane@example.com",
  "password": "correct-horse-battery-staple"
}
```

**Response `200` — no MFA** (token values truncated for readability):

```json
{
  "token_pair": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "user": {
      "id": "0f8fad5b-d9cb-469f-a165-70867728950e",
      "email": "jane@example.com",
      "display_name": "Jane Smith",
      "role": "user",
      "is_active": true,
      "mfa_enabled": false,
      "max_vehicles": 2,
      "free_account": false,
      "obd_enabled": false,
      "obd_auto_connect": false
    }
  },
  "mfa_required": false,
  "mfa_setup_required": false,
  "mfa_token": null
}
```

**Response `200` — MFA required:**

```json
{
  "token_pair": null,
  "mfa_required": true,
  "mfa_setup_required": false,
  "mfa_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Response `200` — MFA setup required (first login):**

```json
{
  "token_pair": null,
  "mfa_required": false,
  "mfa_setup_required": true,
  "mfa_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Errors:** `401` invalid email/password · `403` account disabled · `429` too
many login attempts (temporary IP lockout after 5 failed logins).

**curl**

```bash
curl -s -X POST https://hosted.autobrainservice.app/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","password":"correct-horse-battery-staple"}'
```

### `POST /auth/mfa/verify`

Completes login with a TOTP code when `mfa_required` was returned.

**Request**

```json
{ "mfa_token": "eyJhbGciOiJIUzI1NiIs...", "code": "482913" }
```

**Response `200`** — the real token pair (same shape as `token_pair` above).

### `POST /auth/refresh`

Refresh tokens **rotate on every use** — the presented token is revoked and a
new pair is returned. Keep only the latest pair per device. A password change or
logout invalidates every outstanding token.

**Request**

```json
{ "refresh_token": "eyJhbGciOiJIUzI1NiIs..." }
```

**Response `200`** — a fresh `token_pair`. **Errors:** `401` if the token was
already used, expired, or the account was logged out / password changed.

### `POST /auth/logout`

Revokes **all** sessions for the account by bumping its token version — every
outstanding access and refresh token dies immediately.

**Request** — same body as refresh:

```json
{ "refresh_token": "eyJhbGciOiJIUzI1NiIs..." }
```

**Response `200`**

```json
{ "message": "Logged out — all sessions were revoked" }
```

---

## 3. Reading the current user (`GET`)

### `GET /auth/me`

Returns the authenticated user plus account plan and vehicle-quota info. This is
the canonical "who am I" call for any integration acting as a user.

**Request** (no body)

```http
GET /api/v1/auth/me
Authorization: Bearer <access_token>
```

**Response `200`**

```json
{
  "id": "0f8fad5b-d9cb-469f-a165-70867728950e",
  "email": "jane@example.com",
  "display_name": "Jane Smith",
  "role": "user",
  "is_active": true,
  "mfa_enabled": true,
  "max_vehicles": 2,
  "free_account": false,
  "obd_enabled": false,
  "obd_auto_connect": false,
  "vehicle_count": 1,
  "vehicles_remaining": 1,
  "plan": "enthusiast",
  "subscription_status": "active"
}
```

**Errors:** `401` missing/invalid/expired token.

### `GET /auth/config`

Public, **no auth**. Lets a client decide whether to show signup and how to
behave. Useful for integrations that embed the app's flows.

**Response `200`**

```json
{
  "signup_enabled": true,
  "mfa_enforced": true,
  "license_enabled": false,
  "app_version": "0.3.7"
}
```

### `PATCH /auth/settings`

Self-service account toggles. Users may **only** change `obd_auto_connect`
(everything else is admin-managed). Unknown fields are ignored.

**Request**

```json
{ "obd_auto_connect": true }
```

**Response `200`** — the updated user object (the `/auth/me` shape minus the
plan/vehicle fields).

---

## 4. Admin API — managing users (the core integration)

All routes below are under `/api/v1/admin-api` and require the header:

```http
X-Admin-API-Key: <your-shared-admin-key>
```

### `GET /admin-api/users` — list (the "get")

Optional `?q=` filters by email or display name (case-insensitive substring).

**Request**

```http
GET /api/v1/admin-api/users?q=jane
X-Admin-API-Key: <key>
```

**Response `200`** — a JSON array of users, newest first:

```json
[
  {
    "id": "0f8fad5b-d9cb-469f-a165-70867728950e",
    "email": "jane@example.com",
    "display_name": "Jane Smith",
    "role": "user",
    "is_active": true,
    "mfa_enabled": true,
    "max_vehicles": 2,
    "free_account": false,
    "obd_enabled": false,
    "obd_auto_connect": false,
    "created_at": "2026-08-01T09:15:00Z",
    "pending": false
  }
]
```

### `POST /admin-api/users` — create (the "set")

Creates an account. Pass a `password`, or set `send_invite: true` to email the
user a 7-day set-password link instead. One of the two is required (`422` if
neither).

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `email` | string | — | **required**; must be unique (`409` if taken) |
| `display_name` | string | — | **required**; 1–120 chars; must be unique |
| `password` | string | — | 8–128 chars; required unless `send_invite` |
| `role` | string | `"user"` | `admin` or `user` |
| `max_vehicles` | int | `1` | 1–1000 vehicle quota |
| `send_invite` | bool | `false` | email a setup link instead of a password |
| `free_account` | bool | `false` | `true` disables AI + rego features |
| `obd_enabled` | bool | `false` | grant OBD-II access |

**Request**

```http
POST /api/v1/admin-api/users
X-Admin-API-Key: <key>
Content-Type: application/json

{
  "email": "jane@example.com",
  "display_name": "Jane Smith",
  "password": "correct-horse-battery-staple",
  "role": "user",
  "max_vehicles": 2,
  "free_account": false,
  "obd_enabled": false
}
```

**Response `201`** — the created user (same shape as the list response):

```json
{
  "id": "0f8fad5b-d9cb-469f-a165-70867728950e",
  "email": "jane@example.com",
  "display_name": "Jane Smith",
  "role": "user",
  "is_active": true,
  "mfa_enabled": false,
  "max_vehicles": 2,
  "free_account": false,
  "obd_enabled": false,
  "obd_auto_connect": false,
  "created_at": "2026-08-11T06:30:00Z",
  "pending": false
}
```

**Errors:** `409` email/display name already registered · `422` neither password
nor `send_invite` supplied.

**Send an invite instead of a password:**

```json
{
  "email": "sam@example.com",
  "display_name": "Sam Rivera",
  "send_invite": true
}
```

### `PATCH /admin-api/users/{user_id}` — update (the "set")

Update any subset of fields — send only what changed. `user_id` is the UUID from
a list/create response.

| Field | Type | Notes |
|-------|------|-------|
| `display_name` | string | 1–120 chars |
| `role` | string | `admin` or `user` |
| `is_active` | bool | `false` disables the account |
| `password` | string | 8–128 chars; **revokes all outstanding tokens** and completes a pending invite |
| `max_vehicles` | int | 1–1000 |
| `free_account` | bool | paid ⇄ free switch |
| `obd_enabled` | bool | grant/revoke OBD-II access |
| `obd_auto_connect` | bool | auto-connect toggle |

**Request — promote to admin, raise quota, keep everything else:**

```http
PATCH /api/v1/admin-api/users/0f8fad5b-d9cb-469f-a165-70867728950e
X-Admin-API-Key: <key>
Content-Type: application/json

{
  "role": "admin",
  "max_vehicles": 5
}
```

**Response `200`** — the updated user object.

**Request — disable an account (same as the dedicated disable route):**

```json
{ "is_active": false }
```

### `POST /admin-api/users/{user_id}/disable` — disable

Equivalent to `PATCH … { "is_active": false }`, provided as a single-purpose
route for automation.

**Response `200`** — the updated user object with `"is_active": false`.

### `DELETE /admin-api/users/{user_id}` — delete

Permanently deletes the user, their vehicles, and all their data. Cannot delete
the last `admin` account (`400`).

**Request**

```http
DELETE /api/v1/admin-api/users/0f8fad5b-d9cb-469f-a165-70867728950e
X-Admin-API-Key: <key>
```

**Response `204`** — no body. **Errors:** `404` unknown user · `400` would remove
the last admin.

### Backup / restore (also under `/admin-api`)

For off-box retention you can snapshot the whole database
(`GET /admin-api/backup`, JSON) and its image assets
(`GET /admin-api/assets/backup`, tar.gz), and restore either later
(`POST /admin-api/restore`, `POST /admin-api/assets/restore`). **Restore wipes
the database** — treat these as disaster-recovery tools, not sync endpoints.

---

## 5. Admin user routes (logged-in admin, Bearer auth)

The `/admin/users` routes are the interactive-app equivalents of the Admin API,
authenticated with a user Bearer token where the user has `role: "admin"`.

| Method | Path | Notes |
|--------|------|-------|
| `GET` | `/admin/users?q=&page=` | list; paginated 15/page; returns `{items, total, page, pages}` |
| `POST` | `/admin/users` | create user (same body as Admin API) |
| `PATCH` | `/admin/users/{id}` | update user |
| `POST` | `/admin/users/{id}/re-upgrade?enabled=true` | grant/revoke paid benefits without a Stripe subscription |
| `DELETE` | `/admin/users/{id}` | delete user (cannot be your own account) |
| `GET` | `/admin/version` | server version + GitHub latest-release check |

`POST /auth/register` (admin Bearer) is the token-authenticated equivalent of
creating a user; it returns a fresh `token_pair` for the new account.

---

## 6. End-to-end lifecycle walkthrough

A realistic onboarding automation: create a user, sign in as them, bump their
quota, disable, then delete.

```bash
BASE=https://hosted.autobrainservice.app/api/v1
KEY=<your-admin-api-key>

# 1. Create the user — note the returned "id"
curl -s -X POST $BASE/admin-api/users \
  -H "X-Admin-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","display_name":"Jane Smith","password":"correct-horse-battery-staple","max_vehicles":2}'

# -> id: 0f8fad5b-d9cb-469f-a165-70867728950e

# 2. Sign in as them and extract the access token
TOKEN=$(curl -s -X POST $BASE/auth/login -H "Content-Type: application/json" \
  -d '{"email":"jane@example.com","password":"correct-horse-battery-staple"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token_pair']['access_token'])")

# 3. Confirm identity / quota
curl -s $BASE/auth/me -H "Authorization: Bearer $TOKEN"

# 4. Raise the vehicle quota (Admin API, key-based)
curl -s -X PATCH $BASE/admin-api/users/0f8fad5b-d9cb-469f-a165-70867728950e \
  -H "X-Admin-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"max_vehicles":5}'

# 5. Suspend the account
curl -s -X POST $BASE/admin-api/users/0f8fad5b-d9cb-469f-a165-70867728950e/disable \
  -H "X-Admin-API-Key: $KEY"

# 6. Delete permanently (204, no body)
curl -s -X DELETE $BASE/admin-api/users/0f8fad5b-d9cb-469f-a165-70867728950e \
  -H "X-Admin-API-Key: $KEY"
```

---

## 7. Common status codes

| Code | Meaning |
|------|---------|
| `200` | OK (list/detail/update responses) |
| `201` | Created (user creation) |
| `204` | Deleted — no response body |
| `401` | Bad/expired/missing auth (invalid login, stale token) |
| `403` | Authenticated but not allowed (non-admin on admin routes; demo/free feature locks) |
| `404` | User (or resource) not found |
| `409` | Conflict — email or display name already registered |
| `422` | Validation error — missing/required fields or bad types (see the `detail` array) |
| `429` | Rate limited (5 failed logins per IP → temporary lockout) |

Error bodies follow FastAPI's standard shape. For `422`:

```json
{
  "detail": [
    {
      "loc": ["body", "password"],
      "msg": "String should have at least 8 characters",
      "type": "string_too_short"
    }
  ]
}
```

---

## 8. Where to go from here

- **Explore live:** open the Swagger UI at `https://YOUR-SERVER/docs` — every
  endpoint in this guide can be executed in the browser.
- **Full endpoint list:** `https://YOUR-SERVER/openapi.json` includes every
  route (vehicles, logbook, fuel, services, diagnostics, OBD, mods, receipts,
  parts, valuation, analytics, search, billing, WebSocket), not just the
  account-management surface covered here.
- **More on account policy:** MFA enforcement, roles, quotas and the
  admin-provisioning model are described in `docs/security.md`.
