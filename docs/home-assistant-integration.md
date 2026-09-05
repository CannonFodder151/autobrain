# Home Assistant Integration (AUT-2541)

AutoBrain exposes a lightweight REST surface so Home Assistant (HA) can poll
analytics + service-reminder data for your vehicles. This is the **simplest
possible integration** — no custom HACS add-on required; the `rest` platform
plus a small `command_line` sensor does the work.

## Why this approach

AutoBrain is the **intelligence layer**; HA is the **display/notification
surface**. We only push processed analytics and service-interval data (not raw
telemetry) so the integration stays minimal and deterministic.

## Auth model

1. In AutoBrain → settings (or via API), create a **HA integration token**
   (`POST /api/v1/ha/tokens`).
2. The token is shown **exactly once** (`abha_<64-hex-chars>`).
3. HA polls with `X-HA-API-Key: <token>` on every request.
4. Tokens are scoped per-user (optionally per-vehicle) and can be revoked at
   any time from the AutoBrain UI.

## Endpoints

### User-managed tokens (Bearer JWT required)

| Method | Path | Action |
|--------|------|--------|
| `POST` | `/api/v1/ha/tokens` | Create a new token |
| `GET` | `/api/v1/ha/tokens` | List the user's tokens |
| `DELETE` | `/api/v1/ha/tokens/{id}` | Revoke a token |

Create-body optional fields: `{ "vehicle_id": "<uuid>" }` to scope to one vehicle.

### HA-polled read-only sensors (`X-HA-API-Key`)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/ha/vehicles` | All accessible vehicles |
| `GET` | `/api/v1/ha/vehicles/{id}/service-intervals` | Upcoming service intervals |
| `GET` | `/api/v1/ha/vehicles/{id}/analytics` | Analytics summary |
| `GET` | `/api/v1/ha/service-reminders` | All service reminders across all accessible vehicles |

All endpoints return `application/json`.

## Example HA configuration

```yaml
# configuration.yaml

# Replace these with your actual AutoBrain instance URL + HA token.
rest:
  resource: https://app.autobrainservice.app/api/v1/ha/v1/service-reminders
  headers:
    X-HA-API-Key: "abha_0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
  scan_interval: 3600  # poll every hour
  sensor:
    - name: "AutoBrain Service Reminders"
      value_template: "{{ value_json | length }} reminders"
      json_attributes_path: "$"
      json_attributes: "{{ value_json }}"

# Per-vehicle sensor (repeat for each vehicle you want surfaced in HA).
sensor:
  - platform: rest
    name: "My Car Analytics"
    resource: "https://app.autobrainservice.app/api/v1/ha/v1/vehicles/<VEHICLE_UUID>/analytics"
    headers:
      X-HA-API-Key: "abha_..."
    scan_interval: 1800
    value_template: "{{ value_json.vehicle_nickname }}"
    json_attributes:
      - fuel_total
      - service_total
      - cost_per_km
      - total_km_tracked
```

## Lovelace card example

```yaml
type: entities
entities:
  - entity: sensor.auto_brain_service_reminders
    name: "Service reminders"
  - entity: sensor.my_car_analytics
    name: "My Car"
      attributes:
        fuel_total
        service_total
        cost_per_km
```

## Data model notes

- `service_reminders` pulls from `ServiceRecord` rows where `status="completed"` and `next_due_km` or `next_due_date` is set.
- `due_in_km` = `next_due_km - current_odometer` (clamped to 0).
- `days_until_due` = `(next_due_date - today).days` (clamped to 0).
- Missing or `NULL` fields are `null` in JSON — HA templates should handle this gracefully.

## Security

- Tokens are opaque 256-bit random strings stored as sha256 digests only.
- A prefix index (`api_key_prefix = first 10 chars`) drives lookup; the full
  digest is compared in constant time.
- Tokens are read-only: every HA endpoint is `GET`.
- A `last_used_at` timestamp is updated on every valid call for auditing.
- Revoke tokens immediately from the AutoBrain UI if leaked.
