# AI Models

All modules live in `ai/app/modules/` and are exposed by the gateway at
`/v1/{module}`. AutoBrain is **deterministic-first**: each module runs a
rule-based engine that always produces a valid result, then optionally lets
9Router enrich it. The platform never depends on the router being up — see
`docs/module-breakdown.md` for the per-module breakdown.

## Modules

| Module | Endpoint | Baseline engine | Router's role |
|--------|----------|-----------------|---------------|
| Diagnostics | `/v1/diagnostics` | symptom keyword rules + OBD code table (P0300, P0420, P0171, …) → causes, parts, costs | Repair notes, real-world part numbers |
| Service prediction | `/v1/service-prediction` | manufacturer schedule table per service type, make-specific interval multipliers, measured history intervals | Supplementary interval adjustment |
| OCR | `/v1/ocr` | line-scan heuristics for vendor, date, total, items; local Tesseract for image text | Structured line items |
| Resale | `/v1/resale` | RRP-anchored depreciation curves (base value per make/model, age + odometer + condition + history multipliers); live market-data median anchors the number | Market facts only: `rrp`, `used_price`, AU advice/trend |
| Condition | `/v1/condition` | rule-based estimator from diagnostics (severity-weighted) + service history + odometer vs age (car vs motorcycle scales) | Narrative `summary` only — the label is never overridden |
| Mod impact | `/v1/mod-impact` | per-category performance/value/reliability table | Advice prose |
| Fuel receipt | `/v1/fuel-ocr` | line-scan for vendor, date, litres, price-per-litre, total | Fills only missing optional fields |
| Odometer | `/v1/odometer` | local Tesseract + regex digit scan on the dashboard photo | **None — deterministic-only** |
| Social image | `/v1/social-image` | Pillow on-brand card renderer (title/hook/CTA, 1200x630) | Optional prompt → free Pollinations photo (falls back to deterministic card) |

## Deterministic-first flow

1. The rule engine runs first and its result is the **baseline**.
2. `enhance()` (in `ai/app/router_client.py`) calls 9Router when it is enabled
   and reachable, then **shallow-merges** enrichment fields into the baseline.
3. Keys listed in `_AI_IMMUTABLE` per module are ground truth — the router can
   never override measured numbers, identifiers, currency or value ranges.
4. The result is validated/clamped: `resale` enforces `low ≤ estimated ≤ high`
   (values bounded to a realistic AUD range), odometer clamps to
   `0..9_999_999`.

All router calls run at **temperature 0**.

## `model` field

The response includes a `model` field so callers know which path produced it:

| Value | Meaning |
|-------|---------|
| `rule-based-fallback` | Baseline only (router disabled/unreachable/nothing usable) |
| `rrp-depreciation` | Resale baseline anchored on new-car RRP |
| `rule-based+ai` | Baseline enriched by 9Router (advice/facts only) |

## Fallback engines

`ai/app/fallbacks/` implements the deterministic engines, one module per
feature (`condition.py`, `diagnose.py`, `service_prediction.py`, `ocr.py`,
`resale.py`, `mod_impact.py`, `fuel_ocr.py`, `odometer.py`).

- **Diagnostics:** keyword rules for symptoms (brakes, vibration, leaks,
  noises…) + OBD code table mapped to parts/costs.
- **Service prediction:** manufacturer schedule table per service type with
  make-specific interval multipliers.
- **OCR:** line-scan heuristics for vendor, item hints and totals; Tesseract
  for image input.
- **Resale:** RRP-anchored base value per make/model, age + odometer
  depreciation curves, condition and service-history multipliers.
- **Condition:** severity-weighted open-issue penalty + service coverage /
  recency + odometer vs age (cars 15k km/yr, bikes 6k km/yr) → label
  (excellent/good/fair/poor) + confidence + evidence signals.
- **Mod impact:** per-category performance/value/reliability table.
- **Fuel OCR / Odometer:** line-scan and Tesseract+regex respectively.

## Contract

The gateway posts an OpenAI-style chat completion to the router
(`POST {AI_ROUTER_URL}/chat/completions`) with a strict-JSON system prompt per
module and the payload as the user message; the reply is parsed into the module
output schema. See `docs/ai-router-integration.md`.
