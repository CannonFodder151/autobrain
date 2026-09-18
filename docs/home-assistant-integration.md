# Home Assistant Integration

AutoBrain exposes a REST API for Home Assistant so users can build dashboards,
calendar/todo entities, and automations around service-due alerts and analytics.
All data pushed to HA is **processed analytics + service intervals** (not raw
telemetry). The integration is deterministic (0% AI) and always available.

## Quick setup

1. In AutoBrain: go to **Settings → Home Assistant** → **Create token**.
2. Copy the token (shown once, format `abha_<64-hex>`).
3. In Home Assistant `configuration.yaml`:

```yaml
rest:
  - name: "AutoBrain"
    resource: "https://autobrainservice.app/api/v1/ha/vehicles"
    headers:
      X-HA-API-Key: "abha_xxxxxxxxxxxxxxxx"  # your token
    scan_interval: 300  # 5 min
```

## Authentication

- **User-managed endpoints** (`POST /ha/tokens`, `GET /ha/tokens`, `DELETE /ha/tokens/{id}`):
  Bearer JWT (your normal AutoBrain login token).
- **HA-polled endpoints** (`/ha/vehicles`, `/ha/vehicles/{id}/service-intervals`,
  `/ha/vehicles/{id}/analytics`, `/ha/service-reminders`):
  Header `X-HA-API-Key: abha_<64-hex>` (the token you created).
- Tokens are opaque 256-bit random, shown **once** at creation.
- Stored as sha256 digest only — DB leak cannot be replayed.
- Per-user token (one HA instance = one AutoBrain user).
- Optional `vehicle_id` scope narrows to a single car; NULL = every accessible vehicle.
- `last_used_at` updated on every valid call for auditing.

## Endpoints

### User-managed (Bearer JWT)

| Method | Path | Description |
|--------|------|-------------|
| POST   | `/ha/tokens` | Create token → returns `{id, label, api_key, vehicle_id, created_at}` (**api_key shown once**) |
| GET    | `/ha/tokens` | List your tokens (never returns raw key) |
| DELETE | `/ha/tokens/{id}` | Revoke a token |

### HA-polled (X-HA-API-Key, read-only)

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/ha/vehicles` | All accessible vehicles (owned + accepted-shared) |
| GET    | `/ha/vehicles/{id}/service-intervals` | Upcoming service intervals for a vehicle |
| GET    | `/ha/vehicles/{id}/analytics` | Analytics summary for a vehicle |
| GET    | `/ha/service-reminders` | All upcoming services across all accessible vehicles |

All HA endpoints enforce `get_accessible_vehicle` for vehicle-scoped reads, so
shared vehicles are included but private vehicles are never leaked.

## Rate limits

No dedicated feature flag — HA integration is always available to any active
user. Rate limiting inherits the global `RateLimitMiddleware`; HA polling
cadence is user-controlled on the HA side.

## Vehicle objects

```json
{
  "id": "uuid",
  "nickname": "My Car",
  "make": "Toyota",
  "model": "Corolla",
  "year": 2020,
  "rego": "ABC123",
  "state": "NSW",
  "odometer_km": 45000,
  "club_reg": false,
  "is_shared": false,
  "shared_by": null
}
```

## Service interval object

```json
{
  "id": "uuid",
  "vehicle_id": "uuid",
  "service_type": "interim",
  "due_date": "2026-09-20",
  "due_km": 50000,
  "current_km": 45000,
  "status": "upcoming",
  "confidence": 0.85
}
```

## Analytics object

```json
{
  "vehicle_id": "uuid",
  "total_spend": 3450.00,
  "cost_per_km": 0.12,
  "fuel_efficiency_l_per_100km": 7.2,
  "service_interval_km": 15000,
  "next_service_due": "2026-09-20"
}
```

## Service reminder object

```json
{
  "vehicle_id": "uuid",
  "vehicle_nickname": "My Car",
  "service_type": "major",
  "due_date": "2026-10-15",
  "due_km": 60000,
  "days_until_due": 25,
  "km_until_due": 5000
}
```

## Error handling

- `401` — Missing/invalid `X-HA-API-Key`, deactivated user, or prefix mismatch.
  Never `404` (avoids leaking token existence).
- `403` — Club-reg vehicle accessed (Victoria club reg requires physical logbook).
- `429` — Global rate limit exceeded.

## Phase 2 (planned)

- WebSocket push (`/ws/ha`) for real-time service-reminder updates.
- HACS add-on with config flow (no YAML editing).
- Entity auto-discovery from token scope.

## References

- ADR: [`docs/Engineering/adr/0026-home-assistant-integration.md`](Engineering/adr/0026-home-assistant-integration.md)
- Implementation: `backend/app/api/v1/ha.py`, `backend/app/services/ha_integrations.py`