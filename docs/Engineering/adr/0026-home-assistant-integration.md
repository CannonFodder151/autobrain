# ADR 0026 — Home Assistant Integration: Auth & Endpoint Surface (AUT-2541)

- Status: **Accepted** (Founding Engineer, 2026-09-05; parent AUT-2535)
- Owner: Founding Engineer
- Implements: AUT-2541 (REST) / AUT-2542 (WebSocket) / AUT-2543 (docs)

## Context

AutoBrain needs to push **processed analytics + service-interval data** (not raw
telemetry) to external Home Assistant instances so users can build dashboards,
calendar/todo entities, and automations around service-due alerts.

Phase 1 (MVP) per plan rev `7d1a169e`: REST endpoints + WebSocket push +
docs/examples. REST-only here (AUT-2542 covers WebSocket; out of scope this heartbeat).

## Decision

### 2.1 Auth: per-user token, sha256 digest, prefix index

Mirror the existing **device-key** pattern (`app/services/device_keys.py`) which
the board already accepted for unattended machine auth:

- Tokens are opaque 256-bit random (`abha_<64-hex>`), shown **once** at creation.
- Stored as sha256 digest only — DB leak cannot be replayed.
- `api_key_prefix = first(10)` chars used for an index lookup; full digest
  compared in constant time via `hmac.compare_digest`.
- Per-user token (one HA instance = one AutoBrain user). Optional `vehicle_id`
  scope narrows to a single car; NULL = every accessible vehicle.
- Header: `X-HA-API-Key` (no Bearer, matching `X-Device-API-Key` convention so
  HA's `rest`/`rest.sensor` platforms send it directly).
- `last_used_at` updated on every valid call for auditing.

Rejected alternatives:
- JWT bearer tokens — requires user to obtain/refresh from HA config (no auth UI in HA). Worse UX.
- OAuth / redirect flow — HA add-on config flow lives in Phase 2 (custom HACS integration).
- Sharing a token across users — each HA instance gets its own token.

### 2.2 Endpoint layout

All under `/api/v1/ha/`:

**User-managed** (Bearer JWT):
- `POST /tokens` — create (returns raw key once)
- `GET /tokens` — list (never returns raw key)
- `DELETE /tokens/{id}` — revoke

**HA-polled** (`X-HA-API-Key`, read-only, every endpoint is `GET`):
- `/v1/vehicles` — vehicle list (owned + accepted-shared)
- `/v1/vehicles/{id}/service-intervals` — upcoming service intervals for a vehicle
- `/v1/vehicles/{id}/analytics` — analytics summary
- `/v1/service-reminders` — all upcoming services across all accessible vehicles

All HA endpoints enforce `get_accessible_vehicle` for vehicle-scoped reads, so
shared vehicles are included but private vehicles are never leaked.

### 2.3 401 on every failure path

`get_ha_user` (in `app/api/deps.py`) returns 401 for: missing header, prefix
mismatch, digest mismatch, deactivated user. Never 404 (avoids leaking token
existence).

### 2.4 Data model

`ha_integrations` table mirrors `devices`:

```sql
id              uuid/pk          -- internal
user_id         uuid/fk users    -- index
label           str(80)          -- "Home Assistant" default
api_key_prefix  str(10)          -- index
api_key_hash    str(64)          -- sha256 hex, never the raw key
vehicle_id      uuid/fk vehicles -- nullable scope
last_used_at    timestamptz      -- audit
created_at      timestamptz
```

### 2.5 Config + rate limits

No new feature flags — HA integration is always available to any active user
(token creation is gated by the existing auth dependency). Rate limiting
inherits the global `RateLimitMiddleware`; HA polling cadence is user-controlled
on the HA side.

## Consequences

- Deterministic: 0% AI in this path. All responses derive from existing
  `ServiceRecord` + `FuelLog` + `Modification` aggregates already computed by
  `/analytics` and `/services`.
- Minimal surface: 7 routes. Fits Phase 1 scope.
- Phase 2 (WebSocket + HACS add-on) builds on this token table — `last_used_at`
  already populated.
