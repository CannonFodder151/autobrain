# Home Assistant Integration (AUT-2541/2543)

AutoBrain exposes a lightweight REST surface so Home Assistant (HA) can poll
analytics + service-reminder data for your vehicles. This is the **simplest
possible integration** — no custom HACS add-on required; the `rest` platform
plus a `command_line` sensor does the work.

## Why this approach

AutoBrain is the **intelligence layer**; HA is the **display/notification
surface**. We only push processed analytics and service-interval data (not raw
telemetry) so the integration stays minimal and deterministic.

## Auth model

1. In AutoBrain -> settings (or via the app), create a **HA integration token**
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

## 1 — Configure the REST resource

Add the AutoBrain instance URL and your HA token to `configuration.yaml`.
Replace `https://app.autobrainservice.app` with your deployed host.

```yaml
# configuration.yaml
rest:
  resource: https://app.autobrainservice.app/api/v1/ha/service-reminders
  headers:
    X-HA-API-Key: "abha_0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
  scan_interval: 3600  # poll every hour (seconds)
```

## 2 — Service-reminders sensor

Publish the full `service-reminders` array as a `command_line` sensor so the
list can be used directly in templates, automations and Lovelace cards.

```yaml
# configuration.yaml
sensor:
  - platform: command_line
    name: "AutoBrain Service Reminders"
    command: "curl -s -H 'X-HA-API-Key: <YOUR_TOKEN>' \
      https://app.autobrainservice.app/api/v1/ha/service-reminders"
    scan_interval: 3600
    value_template: "{{ value_json | length }} reminders"
    json_attributes_template: "{{ value_json }}"
```

## 3 — Per-vehicle analytics sensor

```yaml
# configuration.yaml
sensor:
  - platform: rest
    name: "{{ vehicle }} AutoBrain Analytics"
    resource: "https://app.autobrainservice.app/api/v1/ha/vehicles/<VEHICLE_UUID>/analytics"
    headers:
      X-HA-API-Key: "abha_..."
    scan_interval: 1800
    value_template: "{{ value_json.vehicle_nickname }}"
    json_attributes:
      - fuel_total
      - service_total
      - total_cost_of_ownership
      - cost_per_km
      - total_km_tracked
      - count_services
```

The response fields map 1:1 to the API schema defined in
[api-spec.md](api-spec.md).

## 4 — Service-intervals sensor (per vehicle)

```yaml
# configuration.yaml
sensor:
  - platform: rest
    name: "{{ vehicle }} Service Intervals"
    resource: "https://app.autobrainservice.app/api/v1/ha/vehicles/<VEHICLE_UUID>/service-intervals"
    headers:
      X-HA-API-Key: "abha_..."
    scan_interval: 3600
    value_template: "{{ value_json | length }} intervals"
    json_attributes_template: "{{ value_json }}"
```

## 5 — All-vehicles list

```yaml
# configuration.yaml
sensor:
  - platform: rest
    name: "AutoBrain Vehicles"
    resource: "https://app.autobrainservice.app/api/v1/ha/vehicles"
    headers:
      X-HA-API-Key: "abha_..."
    scan_interval: 1800
    value_template: "{{ value_json | length }} vehicles"
    json_attributes_template: "{{ value_json }}"
```

## 6 — HA automation: service-due notifications

Trigger a mobile notification when any vehicle's service is due within 7 days.
The template accesses the `days_until_due` field exposed by the
`/api/v1/ha/service-reminders` endpoint.

```yaml
# automations.yaml
- alias: "AutoBrain - service due soon"
  id: "autobrain_service_due"
  trigger:
    - platform: time_pattern
      minutes: "/30"
  condition: []
  action:
    - service: notify.notify
      data:
        title: "Service reminder"
        message: >
          {% set r = state_attr('sensor.auto_brain_service_reminders', 'auto_brain_service_reminders')
                     | selectattr('days_until_due', 'le', 7) | list | first %}
          {{ 'WARNING: ' + r.vehicle_nickname + ' - ' + r.service_type + ' due in ' + r.days_until_due|string + ' days' if r else 'No service due this week' }}
  mode: single
```

## 7 — HA automation: notification on reminder update

```yaml
# automations.yaml
- alias: "AutoBrain - notify on service reminder"
  id: "autobrain_remind"
  trigger:
    - platform: state
      entity_id: sensor.auto_brain_service_reminders
  action:
    - service: persistent_notification.create
      data:
        title: "AutoBrain: {{ trigger.to_state.state }} reminders"
        message: >
          Check your service intervals:
          {% for r in state_attr('sensor.auto_brain_service_reminders',
                                  'auto_brain_service_reminders') %}
            - {{ r.vehicle_nickname }} - {{ r.service_type }}
              ({{ r.days_until_due }}d / {{ r.due_in_km }} km)
          % endfor %}
  mode: queued
```

## 8 — Lovelace card

```yaml
# ui-lovelace.yaml
type: entities
title: AutoBrain
entities:
  - entity: sensor.auto_brain_service_reminders
    name: "Service reminders"
    secondary_info: last-changed
  - entity: sensor.my_car_auto_brain_analytics
    name: "My Car"
    icon: mdi:car
```

### Markdown card with reminders

```yaml
type: markdown
content: |
  ## AutoBrain reminders

  {% set reminders = state_attr('sensor.auto_brain_service_reminders',
                                  'auto_brain_service_reminders') %}
  {% if reminders %}
    {% for r in reminders %}
    - {{ r.vehicle_nickname }} - **{{ r.service_type }}**
      {% if r.days_until_due is not none %}
        in {{ r.days_until_due }} days
      {% endif %}
      {% if r.due_in_km is not none %}
        (~{{ r.due_in_km }} km)
      {% endif %}
    {% endfor %}
  {% else %}
    No upcoming services.
  {% endif %}
```

## 9 — WebSocket push (AUT-2542, optional)

AutoBrain also supports a `wss://<host>/ws/ha/{vehicle_id}` endpoint that
pushes events in real time. Authentication is the same `abha_` token passed as
the first frame after connect:

```
{"token": "<abha_...>"}
{"event":"service_reminder","payload":{...}}
{"event":"analytics_update","payload":{...}}
```

This path is required for HA automations that must fire exactly once on a
service event. If WebSocket push is enabled, prefer it over the REST polled
sensors above.

## 10 — Data model notes

- `service-reminders` pulls from `ServiceRecord` rows where `status="completed"`
  and `next_due_km` or `next_due_date` is set.
- `due_in_km` = `next_due_km - current_odometer` (clamped to 0).
- `days_until_due` = `(next_due_date - today).days` (clamped to 0).
- Missing or `NULL` fields are `null` in JSON — HA templates should handle this
  gracefully.

## 11 — Security

- Tokens are opaque 256-bit random strings stored as sha256 digests only.
- A prefix index (`api_key_prefix = first 10 chars`) drives lookup; the full
  digest is compared in constant time.
- Every HA endpoint is `GET` (read-only).
- A `last_used_at` timestamp is updated on every valid call for auditing.
- Revoke tokens immediately from the AutoBrain UI if leaked.
