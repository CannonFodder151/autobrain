# AI Modules — Module Breakdown

This document describes each inference module in the AI gateway (`ai/app/`).
AutoBrain is **deterministic-first**: every module runs a rule-based engine that
always produces a valid result, and 9Router only *enriches* that result when it
is reachable. The product never depends on the LLM router being up.

## Design principle

```
rule-based baseline (always)  ──►  enhance()  ──►  validated result
                                   │
                                   └── 9Router (optional): shallow-merge of
                                       enrichment fields only
```

`enhance()` (in `ai/app/router_client.py`):

- Runs the router for the module; if it is disabled/unreachable/errors, returns
  the baseline untouched (`model` stays `rule-based-fallback`).
- When the router responds, it **shallow-merges** its fields into the baseline,
  skipping keys in `_AI_IMMUTABLE` for that module. Immutable keys are
  deterministic ground truth (measurements, identifiers, currency, value
  numbers) and can never be overridden by the model.
- If any non-immutable field was added, `model` becomes `rule-based+ai`.

`model` values observed on results:

| Value | Meaning |
|-------|---------|
| `rule-based-fallback` | Baseline only; router disabled, unreachable, or returned nothing usable |
| `rrp-depreciation` | Resale baseline anchored on the vehicle's new-car RRP (deterministic model) |
| `rule-based+ai` | Baseline enriched by 9Router (advice/facts only — never the measured numbers) |

The **odometer** module is deterministic-only: it never calls the router.

## Modules (`ai/app/modules/`)

| Module | Endpoint | Baseline engine (`ai/app/fallbacks/`) | Router's role | Immutable keys |
|--------|----------|----------------------------------------|----------------|----------------|
| Diagnostics | `/v1/diagnostics` | `diagnose.py` — symptom keyword rules (brakes, vibration, leaks, noises…) + OBD code table (P0300, P0420, P0171, …) mapped to parts/costs | Repair notes, real-world part numbers | — |
| Service prediction | `/v1/service-prediction` | `service_prediction.py` — manufacturer schedule table per service type, make-specific interval multipliers, measured intervals from the vehicle's own history | Supplementary interval adjustment; dates recomputed deterministically | — |
| OCR (receipts) | `/v1/ocr` | `ocr.py` — line-scan heuristics for vendor, item hints, totals; local Tesseract for image text | Enrichment only on non-measured fields (e.g. `next_recommended_service`, `warranty_notes`) — vendor/date/total/tax/currency/items are always the baseline's | `vendor`, `invoice_date`, `total`, `tax`, `currency`, `items` |
| Resale valuation | `/v1/resale` | `resale.py` — RRP-anchored depreciation model (`rrp-depreciation`): base value per make/model, age + odometer depreciation curves, condition and service-history multipliers | Market facts only: new-car `rrp`, typical `used_price`, AU-market advice/trend | `estimated_value`, `low`, `high`, `currency` |
| Mod impact | `/v1/mod-impact` | `mod_impact.py` — per-category performance/value/reliability table | Advice prose on top of the scored baseline | `performance_score`, `value_impact`, `reliability_impact` |
| Fuel receipt OCR | `/v1/fuel-ocr` | `fuel_ocr.py` — line-scan for vendor, date, litres, price-per-litre, total | Only fills optional/missing fields; never the measured numbers | `vendor`, `date`, `litres`, `price_per_litre`, `total_cost`, `currency` |
| Odometer | `/v1/odometer` | `odometer.py` — local Tesseract OCR + regex digit scan on the dashboard photo | **None — deterministic-only** (reads are ~95% accurate, AI adds nothing) | all output |

## Gateway contract

- The gateway exposes `GET /v1/modules` (registry) and `POST /v1/{module}` with
  body `{"payload": {...}}`. An unknown module returns 404.
- `GET /health` returns `{status, service, version, router_url, router_enabled}`
  — a single call tells you whether routing is configured.
- Backend callers use `backend/app/services/ai_client.py` (one `run_*` wrapper
  per module) and receive `{"result": {...}}`.
- All router calls run at **temperature 0**. Numeric output is validated and
  clamped (`resale` enforces `low ≤ estimated ≤ high`, values bounded to a
  realistic AUD range; odometer clamped to `0..9_999_999`).

## Fallbacks package

The rule engines live in the `ai/app/fallbacks/` package — one module per
feature (`diagnose.py`, `service_prediction.py`, `ocr.py`, `resale.py`,
`mod_impact.py`, `fuel_ocr.py`, `odometer.py`). Each exports a single
`*_fallback()` entry point used by the matching `ai/app/modules/` handler.

> When adding a module: add the fallback first, expose it, then layer the
> router enrichment on top. A module must always work with the router down.
