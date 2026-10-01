# Module boundaries

Defines the module layout and ownership boundaries for the AutoBrain **backend**
(`backend/app/`) and the **AI gateway** (`ai/app/`). Routes stay thin; shared
logic lives one layer below so behaviour is enforced once and is easy to test.

## Backend (`backend/app/`)

### `api/v1/` — HTTP routes only
Each file exposes a FastAPI `APIRouter` and **no shared logic of its own**.
Cross-cutting vehicle concerns are imported from the domain modules below.
`vehicles.py` has already graduated to `app/modules/vehicles/` and survives here
as a shim; the rest are still one domain per file.

| File | Owns |
|------|------|
| `vehicles.py` | Backwards-compat shim re-exporting the router from `app/modules/vehicles/api/` |
| `events.py` | Timeline event materialisation (`add_event`), called by other routers after writes |
| `fuel.py`, `services.py`, `diagnostics.py`, `logbook.py`, `mods.py`, `parts.py`, `receipts.py`, `obd.py`, `shares.py`, `valuation.py`, `search.py`, `analytics.py`, `billing.py`, `notifications.py`, `auth.py`, `admin.py`, `admin_api.py` | One domain per file; vehicle-scoped files depend on `ownership` / `events`, never on `vehicles.py` helpers |

**Rule:** no router imports helpers from another router file. Shared vehicle
rules live in `app/modules/vehicles/services/ownership.py`; timeline events in
`events.py`.

### `modules/<domain>/` — self-contained vertical slices
Each domain owns all four of its layers instead of scattering them across
`models/`, `schemas/`, `services/` and `api/v1/`. Layers may only import
downward:

```
app/modules/vehicles/
├── models/vehicle.py     Vehicle, VehicleEvent, PowertrainType
├── schemas/vehicle.py    VehicleCreate/Out/Update, RegoLookup*, Share*
├── services/             ownership, odometer, rego, vehicle business logic
└── api/vehicles.py       the FastAPI /vehicles router
```

| Rule | Enforced by |
|------|-------------|
| `models` imports nothing from `schemas`/`services`/`api` | `.importlinter` + `test_module_boundaries.py` |
| `schemas` imports only from `models` | same |
| `services` imports from `models`/`schemas`, never `api` | same |
| `api` imports from all three below it | same |
| One domain never imports another domain's internals | same |
| A domain's `__init__.py` imports nothing (lazy, avoids a cycle through `app.models`) | `test_module_boundaries.py` |

Run the contracts locally with `cd backend && lint-imports`; the offline AST
guard runs with `python -m pytest tests/test_module_boundaries.py`.

Legacy import paths (`app.models.vehicle`, `app.schemas.vehicle`,
`app.services.{rego,odometer,ownership,vehicle}`, `app.api.v1.vehicles`) are
thin re-export shims, so the ~80 existing call sites are unchanged.
`test_legacy_paths_are_shims` fails if one starts reimplementing code instead
of re-exporting — that guard is what stops a "copy instead of move" split from
forking the domain.

### `services/` — business logic + external integrations
Async-first. Routers call services directly; services never import routers.

| Module | Owns |
|--------|------|
| `backup.py` | Full-DB serialize/restore + per-user backup/import (`serialize_all`, `restore_all`, `serialize_user`, `restore_user_data`, `import_user`, `delete_user_complete`) |
| `odometer.py`, `rego.py`, `ownership.py`, `vehicle.py` | Backwards-compat shims; the implementations moved to `app/modules/vehicles/services/` |
| `ai_client.py` | Backend → AI gateway calls (one wrapper per module) |
| `billing.py`, `email.py`, `notify.py`, `export.py`, `search.py`, `vector_search.py` | Stripe billing, email delivery, push notifications, exports, (vector) search |

### Other `app/` layers
- `models/` — SQLAlchemy models, one file per domain + `models/__init__.py` barrel.
- `schemas/` — Pydantic request/response schemas, one file per domain.

Domains that have graduated to `modules/<domain>/` keep a re-export shim at
their old `models/`/`schemas/`/`services/`/`api/v1/` path so the rest of the
codebase does not have to change in the same commit.
- `core/`, `db/`, `api/deps.py` — config, DB session, auth/entitlement deps.

## AI gateway (`ai/app/`)

### `modules/` — inference entry points (one per capability)
Each `modules/*.py` exposes `run(payload)` registered in `modules/MODULES`.
Deterministic-first: it always computes the rule-based baseline first, then
(where a router is available) calls `router_client.enhance()` so 9Router only
fills/refines optional fields — measured values are never overridden.

### `fallbacks/` — deterministic engines (one module per domain)
Pure functions, no I/O, same output schema as the router path. The 11 domains:

| Fallback module | Provides |
|-----------------|----------|
| `diagnose.py` | `diagnose_fallback` (symptom + OBD rules) |
| `service_prediction.py` | `predict_service_fallback` (manufacturer intervals) |
| `resale.py` | `estimate_value_fallback`, `rrp_for` (AU market anchors + RRP depreciation); also `_mod_value_impact` shared with mod-impact |
| `mod_impact.py` | `mod_impact_fallback` (depends on `resale._mod_value_impact`) |
| `ocr.py` | `extract_receipt_fallback`, `_extract_date` (shared by fuel-ocr) |
| `fuel_ocr.py` | `_fuel_receipt_fallback` (uses `ocr._extract_date`) |
| `odometer.py` | `_odometer_fallback` (regex over OCR text) |
| `parts_guide.py` | `parts_guide_fallback` (SCA taxonomy normalisation + service-type prefill) |
| `advisor.py` | `advisor_fallback` (composes Value/Replace/Upgrade/Finance/Dream sub-modules) |
| `car_check.py` | `car_check_fallback` (listing fields + deal score) |
| `condition.py` | `estimate_condition` (label from vehicle context, diagnostics, history, mods) |

`social_image.py` uses Pillow (always available) and is deterministic-first; it is not in `fallbacks/` because it is self-contained.

### `router_client.py` — the single 9Router client
`enhance()` posts to 9Router with `_AI_IMMUTABLE`-protected fields so AI can
never override deterministic ground truth. No module talks to the router
directly.

## Ownership map
```
HTTP route (api/v1/*)
   ├─ events.py                        (shared timeline events)
   └─ app/modules/<domain>/api         (adapter edge)
        └─ <domain>/services           (business logic + external calls)
             ├─ <domain>/schemas
             └─ <domain>/models
                  └─ ai_client.py ──▶ ai gateway /v1/{module}
                                        └─ modules/*.py
                                             ├─ fallbacks/*  (deterministic baseline)
                                             └─ router_client.enhance() ─▶ 9Router
```
Adding a route: put the handler in the right `api/v1` file, or — for a domain
that lives under `app/modules/<domain>/` — in that domain's `api/` layer. Reuse
`app.modules.vehicles.services.ownership.get_accessible_vehicle` /
`require_ai_vehicle` and `events.add_event` rather than reimplementing them.
Deterministic logic always lands in `ai/app/fallbacks/`, one module per domain.
