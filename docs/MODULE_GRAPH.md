# AutoBrain Module Graph

This document defines the explicit module boundaries and contracts for AutoBrain.

## Module Registry

### Backend Modules (`backend/app/modules/`)

| Module | Purpose | Public API | Internal Deps |
|--------|---------|------------|---------------|
| `auth` | Authentication & authorization | `get_current_user`, `require_*`, `create_access_token` | `app.api.deps`, `app.services.auth` |
| `vehicles` | Vehicle management | `sync_odometer`, `get_market_data`, `check_ownership` | `app.services.odometer`, `app.services.market_data`, `app.services.ownership` |
| `fuel` | Fuel tracking & analytics | `compute_fuel_stats`, `recompute_efficiency`, `extract_fuel_receipt` | `app.services.fuel` |
| `diagnostics` | Vehicle diagnostics | `run_diagnostics`, `predict_service` | `app.services.ai_client` |
| `ai_client` | AI gateway HTTP client | `run_diagnostics`, `predict_service`, `extract_*`, `estimate_*`, `run_advisor_ai`, `run_car_check_ai` | `app.services.ai_client` |
| `social` | Community garage | `SocialIssuePost`, `register_with_hub`, `upload_social_media`, ... | `app.social.*` |

### AI Modules (`ai/app/modules/`)

| Module | Purpose | Contract | Deterministic Fallback |
|--------|---------|----------|------------------------|
| `advisor` | Ownership advisor | `run(payload)` → `{decision, confidence, rationale, next_actions}` | `app.fallbacks.advisor` |
| `car_check` | Deal analysis | `run(payload)` → `{deal_score, red_flags, green_flags}` | `app.fallbacks.car_check` |
| `condition` | Vehicle condition | `run(payload)` → `{condition_score, factors}` | `app.fallbacks.condition` |
| `diagnostics` | OBD diagnostics | `run(payload)` → `{dtc_codes, suggestions}` | `app.fallbacks.diagnose` |
| `fuel_ocr` | Fuel receipt OCR | `run(payload)` → `{vendor, amount, litres, date}` | `app.fallbacks.fuel_ocr` |
| `mod_impact` | Modification impact | `run(payload)` → `{power_delta, value_delta}` | `app.fallbacks.mod_impact` |
| `ocr` | General OCR | `run(payload)` → `{text, confidence}` | `app.fallbacks.ocr` |
| `odometer` | Odometer reading | `run(payload)` → `{reading, confidence}` | `app.fallbacks.odometer` |
| `parts_guide` | SCA parts guide | `run(payload)` → `{parts_list, fitment}` | `app.fallbacks.parts_guide` |
| `resale` | Resale valuation | `run(payload)` → `{value_range, comparables}` | `app.fallbacks.resale` |
| `service_prediction` | Service prediction | `run(payload)` → `{due_services, mileage_estimate}` | `app.fallbacks.service_prediction` |
| `social_image` | Social image analysis | `run(payload)` → `{tags, moderation}` | (no fallback) |

### Frontend Modules (`frontend/lib/`)

| Module | Purpose | Key Exports |
|--------|---------|-------------|
| `core/connectivity_service` | Network state | `ConnectivityService` |
| `services/car/car_kit_service` | CarKit (OBD) | `CarKitService`, `CarKitConnection` |
| `services/dongle/dongle_ble` | ESP32 dongle BLE | `DongleBLE`, `DongleProvisioning` |
| `services/obd/obd_trip_monitor` | OBD trip recording | `OBTTripMonitor` |
| `services/fuel_prices_api` | Fuel prices API | `FuelPricesApi` |
| `services/iap_service` | In-app purchases | `IAPService` |

---

## Module Dependency Graph

### Backend → Backend (Internal)

```
app.api.v1.auth          → app.modules.auth
app.api.v1.vehicles      → app.modules.vehicles
app.api.v1.fuel          → app.modules.fuel, app.modules.ai_client
app.api.v1.diagnostics   → app.modules.diagnostics, app.modules.ai_client
app.api.v1.advisor       → app.modules.ai_client, app.modules.vehicles
app.api.v1.social        → app.modules.social
app.services.fuel        → app.modules.ai_client (via extract_fuel_receipt)
app.services.odometer    → app.modules.ai_client (via read_odometer)
app.services.advisor     → app.modules.ai_client (via run_advisor_ai)
app.services.ownership   → app.modules.vehicles (via check_ownership)
```

### Backend → AI (Cross-Service)

```
app.modules.ai_client (HTTP client)
    → ai service /v1/{module} endpoints
    → ai/app/modules/{module}.run(payload)
```

### AI Internal

```
ai/app/modules/{module}.run
    → app.fallbacks.{module} (deterministic baseline)
    → app.router_client.enhance() (optional AI enrichment)
    → 9Router (http://10.0.3.17:20128/v1)
```

### Frontend → Backend

```
Frontend screens → frontend/lib/services/* → HTTP → backend/app/api/v1/*
```

---

## Module Contracts (Type Signatures)

### `app.modules.auth`

```python
async def get_current_user(token: str = Depends(...), db: AsyncSession = Depends(...)) -> User
async def require_admin(user: User = Depends(get_current_user)) -> User
async def require_write(user: User = Depends(get_current_user)) -> User
async def require_ai(user: User = Depends(get_current_user)) -> User
async def require_premium(user: User = Depends(get_current_user)) -> User
async def require_premium_write(user: User = Depends(require_premium), _: User = Depends(require_write)) -> User
async def require_rego(user: User = Depends(get_current_user)) -> User
async def verify_dongle_server(request: Request) -> None
async def get_device_from_key(request: Request, db: AsyncSession = Depends(...)) -> Device
async def get_ha_user(request: Request, db: AsyncSession = Depends(...)) -> User
async def authenticate_ws(ws: WebSocket, db: AsyncSession) -> User | None
```

### `app.modules.vehicles`

```python
async def sync_odometer(db: AsyncSession, vehicle: Vehicle, source_odo: int | None, ref_time: datetime | None = None) -> bool
async def get_market_data(params: MarketDataParams) -> MarketDataResult
async def check_ownership(db: AsyncSession, user: User, vehicle_id: str) -> bool
```

### `app.modules.fuel`

```python
async def compute_fuel_stats(db: AsyncSession, vehicle_id: str) -> FuelStats
async def recompute_efficiency(db: AsyncSession, vehicle_id: str) -> None
async def link_receipt(db: AsyncSession, vehicle_id: str, receipt_id: str | None) -> str | None
async def extract_fuel_receipt(payload: dict) -> dict | None
```

### `app.modules.ai_client`

```python
async def run_diagnostics(payload: dict) -> dict | None
async def predict_service(payload: dict) -> dict | None
async def extract_receipt(payload: dict) -> dict | None
async def extract_fuel_receipt(payload: dict) -> dict | None
async def read_odometer(payload: dict) -> dict | None
async def estimate_value(payload: dict) -> dict | None
async def mod_impact(payload: dict) -> dict | None
async def estimate_condition(payload: dict) -> dict | None
async def format_sca_parts(payload: dict) -> dict | None
async def run_advisor_ai(vehicle_id: str | None, modules: dict) -> dict | None
async def run_car_check_ai(vehicle_id: str | None, payload: dict) -> dict | None
```

### `app.modules.diagnostics`

```python
async def run_diagnostics(payload: dict) -> dict | None
async def predict_service(payload: dict) -> dict | None
```

### `app.modules.social`

```python
class SocialIssuePost: ...
class SocialComment: ...
class SocialBuild: ...
class SocialFlag: ...
async def register_with_hub(...) -> ...
async def sync_federation(...) -> ...
async def upload_social_media(...) -> ...
async def check_social_rate_limit(...) -> ...
async def create_build_snapshot(...) -> ...
async def get_social_tags(...) -> ...
```

---

## Cross-Cutting Concerns

### Shared Infrastructure (`backend/app/core/`)

| Module | Exports | Used By |
|--------|---------|---------|
| `config` | `settings` | All modules |
| `logging` | `get_logger`, `setup_logging` | All modules |
| `security` | `create_access_token`, `decode_token`, `hash_password` | `auth`, `services.auth`, `services.passkey` |
| `storage` | `ensure_bucket`, `upload_object`, `get_object`, `detect_mime` | `services.fuel`, `services.logbook`, `services.mods`, `social.media` |

### Database Layer (`backend/app/db/`)

| Module | Exports | Used By |
|--------|---------|---------|
| `session` | `get_db`, `init_db`, `AsyncSession` | All services, deps |
| `bootstrap` | `bootstrap()` | Backend startup |

---

## Circular Dependency Analysis

**Result**: No circular dependencies detected at module level.

Verification:
- Backend modules: 0 circular dependencies
- AI modules: 0 circular dependencies
- Cross-service (backend ↔ AI): Acyclic (backend calls AI via HTTP, AI does not call backend)

---

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| Backend module contracts | ✅ Defined | `app.modules.*` created with lazy imports |
| AI module consolidation | ⏳ Planned | 11 → 7 modules |
| Container consolidation | ⏳ Planned | 11 → 7 containers |
| Shared schemas | ⏳ Planned | `shared/schemas/` package |
| Frontend module boundaries | ✅ Clean | No changes needed |

---

## Next Steps

1. **Update API routes** to import from `app.modules.*` instead of `app.services.*`
2. **Consolidate AI modules**: merge `condition+resale→valuation`, `ocr+fuel_ocr+odometer→vision`, `diagnostics+car_check→diagnostics`
3. **Merge AI gateway into backend container** (docker-compose changes)
4. **Remove `gh-runner` container** (use GitHub-hosted runners)
5. **Merge `autobrain-backup` + `backup-agent`** into single backup service
6. **Extract `shared/schemas`** package for cross-repo schema reuse