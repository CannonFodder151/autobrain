# Module Graph

AutoBrain is a three-layer monorepo: **backend** (FastAPI), **AI gateway** (FastAPI), and **frontend** (Flutter). Layers communicate exclusively over HTTP/WS — no cross-layer code imports. Within each layer, modules follow strict dependency directions.

Generated: 2026-09-18 (AUT-3464).

## Cross-layer communication

```
Flutter (iOS/Android/Web)
    │ HTTPS / WSS
    ▼
nginx (:80)
    ├── /api  →  backend :8000
    ├── /ws   →  backend :8000
    └── /ai   →  ai gateway :8001

backend ──HTTP──▶ ai gateway :8001  (via services/ai_client.py)
ai gateway ──HTTP──▶ 9Router       (via router_client.py)
```

**Rule:** no code-level imports between layers. All coupling is over the wire.

## Backend module graph (`backend/app/`)

### Dependency layers (top = depends on, bottom = depended upon)

```
┌─────────────────────────────────────────────────────────────┐
│  api/v1/*  (28 route modules)                               │
│  Thin HTTP handlers. Import: deps, services, models,        │
│  schemas, workers. Never import other route modules.        │
├─────────────────────────────────────────────────────────────┤
│  services/*  (32 modules)                                   │
│  Business logic. Import: models, core, other services.      │
│  Never import api/v1, schemas, middleware, or ws.           │
├─────────────────────────────────────────────────────────────┤
│  schemas/*  (20 modules)                                    │
│  Pydantic request/response contracts. Import: models only.  │
│  Never import services, api, workers.                       │
├─────────────────────────────────────────────────────────────┤
│  models/*  (20 modules)                                     │
│  SQLAlchemy ORM models. Import: db.session.Base only.       │
│  Never import services, schemas, api.                       │
├─────────────────────────────────────────────────────────────┤
│  core/*  |  db/*  |  workers/*  |  ws/  |  middleware/*     │
│  Infrastructure: config, logging, storage, security,        │
│  DB session, Celery, WebSocket, rate limiting.              │
└─────────────────────────────────────────────────────────────┘
```

### Backend → AI boundary

```
services/ai_client.py ──HTTP POST /v1/{module}──▶ ai gateway
```

The backend never imports AI module code. Communication is a single HTTP client wrapper (`_call(module, payload)`) with per-module typed helpers (`run_diagnostics`, `predict_service`, `extract_receipt`, etc.).

### Backend module map

| Domain | api/v1 route | services | models | schemas |
|--------|-------------|----------|--------|---------|
| **Auth** | `auth.py` | `auth.py` | `user.py`, `refresh_token.py` | `auth.py` |
| **Vehicles** | `vehicles.py` | `vehicle.py`, `ownership.py`, `rego.py` | `vehicle.py`, `share.py` | `vehicle.py` |
| **Fuel** | `fuel.py`, `fuel_servo.py`, `fuel_prices.py` | `fuel.py`, `fuel_feeds.py`, `fuel_servo.py`, `fuel_prices.py`, `fuel_source_arbitration.py` | `fuel.py`, `fuel_station.py`, `fuel_price.py`, `receipt.py` | `fuel.py`, `fuel_servo.py` |
| **Advisor** | `advisor.py`, `valuation.py` | `advisor/` (sub-package), `market_data.py` | `market_listing.py`, `valuation.py` | `advisor.py`, `valuation.py` |
| **Diagnostics** | `diagnostics.py`, `obd.py` | `odometer.py`, `events.py` | `diagnostic.py`, `obd.py` | `diagnostic.py`, `obd.py` |
| **Services & Parts** | `services.py`, `parts.py` | `service_records.py`, `parts_guide.py`, `events.py` | `service.py`, `part.py`, `sca_parts.py` | `service.py`, `part.py` |
| **Mods** | `mods.py` | (inline) | `mod.py` | `mod.py` |
| **Logbook** | `logbook.py` | `events.py` | `logbook.py` | `logbook.py` |
| **Receipts** | `receipts.py` | (inline) | `receipt.py` | `receipt.py` |
| **Search** | `search.py` | `search.py`, `vector_search.py` | (none) | (none) |
| **Billing** | `billing.py` | `billing.py`, `iap.py` | (Stripe) | `billing.py` |
| **Devices** | `devices.py`, `dongle_firmware.py` | `device_keys.py`, `ha_keys.py` | `device.py`, `dongle_firmware.py` | `device.py` |
| **Notifications** | `notifications.py` | `notify.py`, `email.py` | `notification.py` | `notification.py` |
| **Social** | `social.py` | `social/` sub-package | `social/models.py` | (social) |
| **HA** | `ha.py` | `ha_keys.py` | `ha.py` | `ha.py` |
| **Backup** | `admin_api.py` | `backup.py`, `assets.py` | (none) | (none) |
| **Analytics** | `analytics.py` | (inline) | (none) | `analytics.py` |
| **CI** | `ci.py` | (none) | (none) | (none) |

### Key intra-service dependencies

```
fuel.py ──▶ ai_client.extract_fuel_receipt
odometer.py ──▶ ai_client.predict_service, service_records, events
parts_guide.py ──▶ ai_client.format_sca_parts, rego.lookup_rego
valuation.py ──▶ ai_client.estimate_value/mod_impact/estimate_condition
advisor/*.py ──▶ market_data.get_market_data
search.py ──▶ vector_search.generate_embedding
iap.py ──▶ billing (subscription checks)
notify.py ──▶ email (delivery)
```

## AI gateway module graph (`ai/app/`)

### Dependency layers

```
┌──────────────────────────────────────────────────┐
│  main.py  (FastAPI app, /v1/{module} router)     │
├──────────────────────────────────────────────────┤
│  modules/*  (12 entry points)                    │
│  Each: run(payload) → dict. Imports: its own     │
│  fallback, router_client.enhance().              │
├──────────────────────────────────────────────────┤
│  fallbacks/*  (deterministic engines)            │
│  Pure functions. Import: other fallbacks for     │
│  shared helpers. Never import modules or router. │
├──────────────────────────────────────────────────┤
│  router_client.py  (9Router HTTP client)         │
│  Single entry point for AI calls.                 │
├──────────────────────────────────────────────────┤
│  router_utils.py  |  ocr_utils.py  |  logging   │
│  Pure utilities, no cross-imports.                │
└──────────────────────────────────────────────────┘
```

### AI module registry

| Module | Module handler | Fallback | Router-enhanced |
|--------|---------------|----------|----------------|
| `advisor` | `modules/advisor.py` | `fallbacks/advisor.py` | Yes |
| `car-check` | `modules/car_check.py` | `fallbacks/car_check.py` | Yes |
| `condition` | `modules/condition.py` | `fallbacks/condition.py` | Yes |
| `diagnostics` | `modules/diagnostics.py` | `fallbacks/diagnose.py` | Yes |
| `fuel-ocr` | `modules/fuel_ocr.py` | `fallbacks/fuel_ocr.py` | Yes |
| `mod-impact` | `modules/mod_impact.py` | `fallbacks/mod_impact.py` | Yes |
| `ocr` | `modules/ocr.py` | `fallbacks/ocr.py` | Yes |
| `odometer` | `modules/odometer.py` | `fallbacks/odometer.py` | No (OCR-only) |
| `parts-guide` | `modules/parts_guide.py` | `fallbacks/parts_guide.py` | Yes |
| `resale` | `modules/resale.py` | `fallbacks/resale.py` | Yes |
| `service-prediction` | `modules/service_prediction.py` | `fallbacks/service_prediction.py` | Yes |
| `social-image` | `modules/social_image.py` | (none) | No (generated) |

### Deterministic-first pattern

Every AI module follows this contract:

```python
async def run(payload: dict) -> dict:
    # 1. Compute deterministic baseline
    baseline = fallback(payload)
    # 2. Optionally enrich via 9Router
    result = await router_client.enhance(MODULE_NAME, payload, baseline)
    # 3. Return — baseline fields are never overridden by AI
    return result
```

`_AI_IMMUTABLE` in `router_utils.py` protects measured/ground-truth fields from being overwritten by the router response.

## Frontend module graph (`frontend/lib/`)

```
┌──────────────────────────────────────────────────┐
│  main.dart → app.dart                            │
├──────────────────────────────────────────────────┤
│  screens/*  (19 domain screen groups)            │
│  Each domain is a subdirectory with its own      │
│  screens, widgets, and local models.             │
├──────────────────────────────────────────────────┤
│  widgets/  (shared: vehicle_selector, responsive,│
│  rego_status_badge, stale_hint, trip_route_map)  │
├──────────────────────────────────────────────────┤
│  services/  (platform: dongle, car, IAP, fuel)   │
├──────────────────────────────────────────────────┤
│  core/  (api_client, auth_state, config,         │
│  connectivity, models, offline_cache, theme)     │
└──────────────────────────────────────────────────┘
```

Frontend communicates with backend exclusively through `core/api_client.dart` (REST) and WebSocket. No direct imports between screen domains.

## Circular dependency analysis

**Cross-layer cycles: none** — enforced by HTTP-only communication.

**Backend internal: no cycles detected** (2026-09-18 audit).

**AI internal: no cycles detected** — unidirectional flow:
```
modules/*.py → fallbacks/*.py → ocr_utils/utils
modules/*.py → router_client → router_utils
```

**Known boundary violations (fixed in AUT-3464):**
- `schemas/device.py` and `schemas/logbook.py` previously imported `app.services.trip_gps.clean_samples`. This violates the schemas → services boundary. Fixed by extracting `clean_samples` to `app/utils/gps.py` (pure utility, no service dependencies).

## Boundary rules

1. **Routes never import other routes.** Shared logic lives in `services/ownership.py` (vehicle access) and `services/events.py` (timeline).
2. **Services never import routes, schemas, middleware, or workers.** Services depend on models and core only.
3. **Schemas never import services.** Schemas are standalone Pydantic contracts.
4. **Models never import services, schemas, or routes.** Models depend on `db.session.Base` only.
5. **AI fallbacks never import modules or router_client.** Fallbacks are pure functions.
6. **No cross-layer code imports.** Backend↔AI is HTTP only. Frontend↔backend is REST/WS only.
