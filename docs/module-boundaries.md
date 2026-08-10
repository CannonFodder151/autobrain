# Module boundaries

Defines the module layout and ownership boundaries for the AutoBrain **backend**
(`backend/app/`) and the **AI gateway** (`ai/app/`). Routes stay thin; shared
logic lives one layer below so behaviour is enforced once and is easy to test.

## Backend (`backend/app/`)

### `api/v1/` — HTTP routes only
Each file exposes a FastAPI `APIRouter` and **no shared logic of its own**.
Cross-cutting vehicle concerns are imported from the modules below.

| File | Owns |
|------|------|
| `vehicles.py` | Vehicle CRUD, rego lookup, timeline, shares |
| `ownership.py` | Vehicle ownership + access rules shared by every vehicle-scoped router: `get_owned_vehicle`, `get_accessible_vehicle`, `effective_feature_owner`, `require_ai_vehicle`, `clear_primary`, `sync_odometer_from_fuel` |
| `events.py` | Timeline event materialisation (`add_event`), called by other routers after writes |
| `fuel.py`, `services.py`, `diagnostics.py`, `logbook.py`, `mods.py`, `parts.py`, `receipts.py`, `obd.py`, `shares.py`, `valuation.py`, `search.py`, `analytics.py`, `billing.py`, `notifications.py`, `auth.py`, `admin.py`, `admin_api.py` | One domain per file; vehicle-scoped files depend on `ownership` / `events`, never on `vehicles.py` helpers |

**Rule:** no router imports helpers from another router file. Shared vehicle
rules live in `ownership.py`; timeline events in `events.py`.

### `services/` — business logic + external integrations
Async-first. Routers call services directly; services never import routers.

| Module | Owns |
|--------|------|
| `backup.py` | Full-DB serialize/restore + per-user backup/import (`serialize_all`, `restore_all`, `serialize_user`, `restore_user_data`, `import_user`, `delete_user_complete`) |
| `odometer.py` | Odometer sync from fuel/service data (`sync_odometer`) |
| `rego.py` | AU rego-lookup API client |
| `ai_client.py` | Backend → AI gateway calls (one wrapper per module) |
| `billing.py`, `email.py`, `notify.py`, `export.py`, `search.py`, `vector_search.py`, `version.py` | Stripe billing, email delivery, push notifications, exports, (vector) search, version check |

### Other `app/` layers
- `models/` — SQLAlchemy models, one file per domain (12 files + `models/__init__.py` barrel).
- `schemas/` — Pydantic request/response schemas, one file per domain.
- `core/`, `db/`, `api/deps.py` — config, DB session, auth/entitlement deps.

## AI gateway (`ai/app/`)

### `modules/` — inference entry points (one per capability)
Each `modules/*.py` exposes `run(payload)` registered in `modules/MODULES`.
Deterministic-first: it always computes the rule-based baseline first, then
(where a router is available) calls `router_client.enhance()` so 9Router only
fills/refines optional fields — measured values are never overridden.

### `fallbacks/` — deterministic engines (one module per domain)
Pure functions, no I/O, same output schema as the router path. The 7 domains:

| Fallback module | Provides |
|-----------------|----------|
| `diagnose.py` | `diagnose_fallback` (symptom + OBD rules) |
| `service_prediction.py` | `predict_service_fallback` (manufacturer intervals) |
| `resale.py` | `estimate_value_fallback`, `rrp_for` (AU market anchors + RRP depreciation); also `_mod_value_impact` shared with mod-impact |
| `mod_impact.py` | `mod_impact_fallback` (depends on `resale._mod_value_impact`) |
| `ocr.py` | `extract_receipt_fallback`, `_extract_date` (shared by fuel-ocr) |
| `fuel_ocr.py` | `_fuel_receipt_fallback` (uses `ocr._extract_date`) |
| `odometer.py` | `_odometer_fallback` (regex over OCR text) |

`fallbacks/__init__.py` is a barrel that re-exports the public symbols so
`from app.fallbacks import ...` keeps working. Modules import from their
specific domain file.

### `router_client.py` — the single 9Router client
`enhance()` posts to 9Router with `_AI_IMMUTABLE`-protected fields so AI can
never override deterministic ground truth. No module talks to the router
directly.

## Ownership map
```
HTTP route (api/v1/*)
   └─ ownership.py / events.py   (shared vehicle rules)
   └─ services/*                 (business logic + external calls)
        └─ ai_client.py ──────▶ ai gateway /v1/{module}
                                     └─ modules/*.py
                                          ├─ fallbacks/*  (deterministic baseline)
                                          └─ router_client.enhance() ─▶ 9Router
```
Adding a route: put the handler in the right `api/v1` file, reuse
`ownership.get_accessible_vehicle` / `require_ai_vehicle` and `events.add_event`
rather than reimplementing them. Deterministic logic always lands in
`ai/app/fallbacks/`, one module per domain.
