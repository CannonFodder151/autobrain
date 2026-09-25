# AutoBrain AI Reliability Pattern

## Overview

All AutoBrain AI features follow a **deterministic-first** pattern: a rule-based, local, always-available baseline runs first, and 9Router is consulted only as an optional enhancer. This makes AutoBrain resilient to router outages, cost spikes, and network failures.

## Core Principles

1. **Deterministic baseline is authoritative** — The rule engine always runs and produces the primary result
2. **AI is an enhancer, not the source of truth** — 9Router may add narrative, formatting, or supplementary context
3. **Critical fields are immutable** — AI cannot override numbers, decisions, or classifications produced by the baseline
4. **Fail closed on validation** — AI responses are validated, clamped, and sanitized before reaching callers
5. **Same schema both paths** — Baseline and AI-enhanced results share identical output contracts

## Architecture

```
Client Request
    │
    ▼
Backend (FastAPI)
    │
    ├──► Deterministic baseline (rule engine) ──► Validated result ──► Client
    │        │
    │        └──► AI enhancement (9Router, optional) ──► Merged result ──► Client
    │
    └──► Cache (24h, per-input) ──► Reuse existing result
```

## Module Pattern

Every AI module in `ai/app/modules/` follows this structure:

```python
from app.fallbacks.<module> import <fallback_function>
from app.router_client import enhance

async def run(payload: dict) -> dict:
    baseline = <fallback_function>(payload)
    merged = await enhance("<module-name>", payload, baseline)
    return <validate_function>(merged)
```

## Example: Diagnostics

```python
# ai/app/modules/diagnostics.py
from app.fallbacks.diagnose import diagnose_fallback
from app.router_client import enhance

async def run(payload: dict) -> dict:
    baseline = diagnose_fallback(
        payload.get("symptoms", ""),
        payload.get("vehicle"),
        payload.get("obd_codes"),
    )
    return await enhance("diagnostics", payload, baseline)
```

The rule engine uses OBD codes + symptom keyword rules. 9Router only enriches repair notes / part numbers.

## Example: Advisor

```python
# ai/app/modules/advisor.py
from app.fallbacks.advisor import advisor_fallback, validate_advisor_response
from app.router_client import enhance

async def run(payload: dict) -> dict:
    baseline = advisor_fallback(payload or {})
    merged = await enhance("advisor", payload or {}, baseline)
    return validate_advisor_response(merged)
```

The baseline decides `keep` / `upgrade` / `delay` / `strategy` from deterministic rules. The `decision` field is immutable — AI cannot override it.

## Immutable Fields

Each module declares `_AI_IMMUTABLE` keys that the router cannot change:

| Module | Immutable Keys |
|--------|---------------|
| `advisor` | `decision`, `confidence` |
| `car-check` | `deal_score` |
| `condition` | `condition`, `score` |
| `diagnostics` | `dtc_codes`, `severity` |
| `fuel-ocr` | `vendor`, `litres`, `price_per_litre`, `total_cost` |
| `ocr` | `vendor`, `total`, `tax`, `items` |
| `odometer` | `reading`, `confidence` |
| `resale` | `estimated_value`, `low`, `high` |
| `service-prediction` | `next_service`, `due_services` |
| `mod-impact` | `power_delta`, `value_delta` |

## Merge Behavior (`app/router_client.py::enhance`)

```python
async def enhance(module: str, payload: dict, baseline: dict) -> dict:
    result = await route(module, payload)
    if not isinstance(result, dict):
        return baseline

    immutable = _AI_IMMUTABLE.get(module, frozenset())
    schema = _SCHEMAS.get(module, {})
    merged = dict(baseline)
    enriched = False
    for key, value in result.items():
        if key == "model" or key in immutable:
            continue
        if key not in schema or not _matches_type(value, schema[key]):
            continue
        if not _validate_nested(value):
            continue
        merged[key] = value
        enriched = True
    if enriched:
        merged["model"] = "rule-based+ai"
    return merged
```

## Router Failure Handling

- **Unreachable router** → `route()` returns `None` → baseline returned untouched
- **Invalid response** → `route()` returns `None` → baseline returned untouched
- **Oversized response** → `route()` returns `None` → baseline returned untouched
- **HTTP error** → `route()` returns `None` → baseline returned untouched
- **AI disabled** (`AI_ENABLED=false`) → `route()` returns `None` → baseline returned untouched

## Validation & Sanitization

Every module validates and clamps AI output:

- **Numbers** → Parsed to floats, clamped to sane ranges
- **Enums** → Validated against allowed values, default applied on invalid
- **Strings** → Trimmed, length-clamped
- **Lists** → Type-checked, truncated
- **Nested objects** → Recursively validated
- **Unknown keys** → Dropped with warning logs

## Caching

The backend caches AI results to avoid repeat 9Router calls:

```python
# app/services/ai_client.py
_ADVISOR_CACHE_TTL_SECONDS = 24 * 60 * 60
_ADVISOR_CACHE_MAX_ENTRIES = 1024
```

- Cache key: `(vehicle_id, stable module-outputs hash)`
- Same inputs = same answer for 24h
- Per-process cache (restart-eviction acceptable)

## Module Inventory

| Module | Endpoint | Baseline | AI Role |
|--------|----------|----------|---------|
| `advisor` | `/v1/advisor` | Decision tree (keep/upgrade/delay/strategy) | Enrich rationale + next_actions |
| `car-check` | `/v1/car-check` | Deal score + listing analysis | Narrative summary |
| `condition` | `/v1/condition` | Rule-based condition score | Narrative summary |
| `diagnostics` | `/v1/diagnostics` | OBD codes + symptom keyword rules | Repair notes + part numbers |
| `fuel-ocr` | `/v1/fuel-ocr` | Tesseract + receipt parsing | Polish optional fields |
| `mod-impact` | `/v1/mod-impact` | Category lookup table | Narrative summary |
| `ocr` | `/v1/ocr` | Tesseract + receipt parsing | Line-item classification polish |
| `odometer` | `/v1/odometer` | Tesseract + regex (no router) | N/A (deterministic-only) |
| `resale` | `/v1/resale` | Depreciation curve + market data | Market facts + advice |
| `service-prediction` | `/v1/service-prediction` | Manufacturer schedules + measured intervals | Supplementary adjustment |
| `parts-guide` | `/v1/parts-guide` | SCA category normalisation | Description/brand tidy |
| `social-image` | `/v1/social-image` | Branded card renderer (Pillow) | Optional photoreal image |

## Model Field Semantics

The `model` field tells callers which path produced the result:

- `"rule-based-fallback"` — Baseline only (router down or disabled)
- `"rule-based"` — Baseline only (module is deterministic-only)
- `"rule-based+ai"` — Baseline + AI enhancement
- `<router-model>` — Router response (rare, only when baseline unavailable)

## Cost Control

- **Deterministic-first** — Most calls never touch the router
- **24h cache** — Repeat calls reuse existing results
- **Per-user rate limits** — Backend enforces fixed-window caps before 9Router spend
- **Global gateway limits** — In-memory caps protect against runaway callers
- **AI_ENABLED toggle** — Kill switch for all AI features

## Testing

Each module has unit tests covering:

- Baseline correctness
- Router-unreachable fallback
- Immutable field protection
- Validation and clamping
- Cache behaviour

Run with:

```bash
cd backend
pytest tests/test_advisor_ai.py tests/test_advisor_dream.py tests/test_advisor_finance.py tests/test_advisor_module_boundaries.py tests/test_advisor_replace.py tests/test_advisor_upgrade.py tests/test_advisor_value.py tests/test_car_check.py tests/test_car_check_ai.py
```

---

*Generated as part of Phase 1 Code Review & Improvement Initiative (AUT-XXXX). Last updated: 2026-09-24.*