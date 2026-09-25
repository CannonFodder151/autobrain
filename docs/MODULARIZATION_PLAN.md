# AutoBrain Modularization Plan

## Executive Summary

This document outlines the modularization strategy for AutoBrain's codebase, targeting:
1. Clear module boundaries and contracts
2. Reduced coupling between `backend/`, `ai/`, and `frontend/`
3. Container consolidation (11 → 7 containers)
4. Elimination of circular dependencies
5. Shared schema contracts

---

## Current Architecture Analysis

### Container Count (Hosted Stack)

| Container | Purpose | Dependency |
|-----------|---------|------------|
| postgres | Database | - |
| redis | Message broker | - |
| minio | Object storage | - |
| backend | FastAPI + Celery | postgres, redis, minio |
| ai | AI Gateway + market-data | backend |
| frontend | Flutter web | backend, ai |
| hub | Federation hub | backend |
| dongle-server | Firmware service | backend |
| gh-runner | CI runner | - |
| 9router | AI router | - |
| autobrain-backup | Backup GUI | - |
| backup-agent | Backup poller | backend, autobrain-backup |

### Module Dependencies

#### Backend (`backend/app/`)
- **API Layer**: 28 v1 routes, each importing 5-15 modules
- **Services Layer**: 30+ services, many importing each other
- **Core**: config, logging, security, storage
- **Models**: 20+ SQLAlchemy models
- **Schemas**: 20+ Pydantic schemas

**Key Coupling Points:**
- `api.deps` → auth, user, device models, security, services
- `services` → core.config, core.logging, models
- Services import each other (fuel → ai_client, events, odometer)

#### AI Gateway (`ai/app/`)
- **Modules**: 11 modules (advisor, car_check, condition, diagnostics, fuel_ocr, mod_impact, ocr, odometer, parts_guide, resale, service_prediction, social_image)
- **Pattern**: Each module = deterministic fallback + AI enhancement
- **Router Client**: 9Router integration

**Status**: Well-structured, minimal coupling

#### Frontend (`frontend/lib/`)
- **Screens**: Organized by feature
- **Services**: car/, dongle/, obd/, fuel_prices, iap
- **Core**: connectivity_service.dart

**Status**: Clean separation, minimal cross-module imports

---

## Modularization Plan

### Phase 1: Backend Module Extraction

#### 1.1 Create Domain Modules

Group related services into domain modules:

```
backend/app/
├── core/                    # Shared infrastructure (unchanged)
│   ├── config.py
│   ├── logging.py
│   ├── security.py
│   └── storage.py
├── modules/
│   ├── auth/                # Authentication module
│   │   ├── __init__.py
│   │   ├── api.py           # /api/v1/auth endpoints
│   │   ├── service.py       # auth business logic
│   │   ├── models.py        # User, Passkey, RefreshToken
│   │   ├── schemas.py       # TokenPair, UserOut, MfaSetupResponse
│   │   └── deps.py          # get_current_user, authenticate_ws
│   ├── vehicles/            # Vehicle management module
│   │   ├── __init__.py
│   │   ├── api.py
│   │   ├── service.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── fuel/                # Fuel tracking module
│   │   ├── __init__.py
│   │   ├── api.py
│   │   ├── service.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── diagnostics/         # Diagnostics module
│   │   ├── __init__.py
│   │   ├── api.py
│   │   ├── service.py
│   │   ├── models.py
│   │   └── schemas.py
│   ├── ai_client/           # AI gateway client module
│   │   ├── __init__.py
│   │   └── client.py        # HTTP client to ai service
│   └── social/              # Community garage module
│       ├── __init__.py
│       ├── api.py
│       ├── service.py
│       ├── models.py
│       └── schemas.py
└── workers/                 # Celery tasks (unchanged)
```

#### 1.2 Define Module Interfaces

Each module exposes a public API via `__init__.py`:

```python
# backend/app/modules/vehicles/__init__.py
from .service import VehicleService
from .models import Vehicle
from .schemas import VehicleOut, VehicleCreate

__all__ = ["VehicleService", "Vehicle", "VehicleOut", "VehicleCreate"]
```

#### 1.3 Eliminate Cross-Module Service Imports

**Before:**
```python
# services/fuel.py
from app.services import ai_client, events, odometer
```

**After:**
```python
# modules/fuel/service.py
from app.modules.ai_client import AIClient
from app.modules.diagnostics import DiagnosticsService
```

---

### Phase 2: AI Module Consolidation

#### 2.1 Merge Overlapping Modules

Current: 11 modules with some overlap

**Merge Strategy:**
- `condition` + `resale` → `valuation` (car valuation module)
- `ocr` + `fuel_ocr` + `odometer` → `vision` (image processing module)
- `diagnostics` + `car_check` → `diagnostics` (vehicle health)

**Result:** 7 modules (down from 11)

#### 2.2 Create AI Module Registry

```python
# ai/app/modules/__init__.py
MODULES = {
    "advisor": advisor.run,
    "valuation": valuation.run,      # merged condition + resale
    "vision": vision.run,            # merged ocr + fuel_ocr + odometer
    "diagnostics": diagnostics.run,  # merged diagnostics + car_check
    "service-prediction": service_prediction.run,
    "mod-impact": mod_impact.run,
    "parts-guide": parts_guide.run,
    "social-image": social_image.run,
}
```

---

### Phase 3: Container Consolidation

#### 3.1 Target Architecture

| Container | Purpose | Change |
|-----------|---------|--------|
| postgres | Database | - |
| redis | Message broker | - |
| minio | Object storage | - |
| backend | FastAPI + Celery + AI Gateway | **Merged** |
| frontend | Flutter web | - |
| dongle-server | Firmware service | - |
| 9router | AI router | - |

**Result:** 7 containers (down from 11)

#### 3.2 Merge AI into Backend

Move AI gateway into backend container:

```yaml
# docker-compose.hosted.yml
backend:
  image: ghcr.io/cannonfodder151/autobrain-backend:latest
  command: >-
    sh -c "
    python -m app.db.bootstrap
    && (celery -A app.workers.celery_app worker -B -l info --concurrency=2 &)
    && (uvicorn ai_app.main:app --host 0.0.0.0 --port 8001 &)
    && exec uvicorn app.main:app --host 0.0.0.0 --port 8000
    "
```

#### 3.3 Remove Deprecated Containers

- Remove `hub` (integrate into backend or keep external)
- Remove `gh-runner` (use GitHub-hosted runners)
- Remove `autobrain-backup` + `backup-agent` (integrate into backend)

---

### Phase 4: Shared Schema Contracts

#### 4.1 Create Shared Schemas Package

```
shared/
└── schemas/
    ├── __init__.py
    ├── vehicle.py      # VehicleOut, VehicleCreate
    ├── fuel.py         # FuelLogOut, FuelStats
    ├── diagnostic.py   # DiagnosticOut
    └── valuation.py    # ValuationOut
```

#### 4.2 Backend + AI Import from Shared

```python
# backend/app/modules/vehicles/schemas.py
from shared.schemas.vehicle import VehicleOut, VehicleCreate

# ai/app/modules/valuation/schemas.py
from shared.schemas.valuation import ValuationOut
```

---

## Implementation Timeline

### Week 1-2: Backend Module Extraction
- Create domain modules
- Extract api.deps → module-specific deps
- Update imports

### Week 3: AI Module Consolidation
- Merge overlapping modules
- Update fallback logic
- Test inference paths

### Week 4: Container Consolidation
- Merge AI into backend container
- Remove deprecated containers
- Update docker-compose files

### Week 5: Shared Schemas
- Extract common schemas
- Update imports
- Validate consistency

---

## Risk Mitigation

1. **Backward Compatibility**: Keep old imports working via re-exports
2. **Testing**: Run full test suite after each phase
3. **Deployment**: Canary rollout (10% → 50% → 100%)
4. **Rollback**: Maintain previous container images

---

## Success Metrics

- **Container Count**: 11 → 7 (36% reduction)
- **Circular Dependencies**: 0 → 0 (maintain)
- **Module Coupling**: Reduce cross-module imports by 50%
- **AI Inference Latency**: No regression
- **Backend Startup Time**: < 30 seconds
