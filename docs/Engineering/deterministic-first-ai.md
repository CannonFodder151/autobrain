# Deterministic-First AI Pattern

AutoBrain's AI integration follows a **deterministic-first, AI-fallback** design. Every AI module runs a rule-based engine first; the 9Router LLM only enriches — never replaces — deterministic output. If the router is down, the platform degrades gracefully to deterministic-only mode with zero user-facing impact.

---

## Core Principles

1. **Baseline always runs.** The rule-based fallback produces a complete result before any router call.
2. **Router enriches only.** AI may fill gaps, add advice, or refine narrative — but never overrides deterministic ground-truth values.
3. **Immutable keys are protected.** Per-module `_AI_IMMUTABLE` sets block the router from overwriting measured fields (currency, measurements, IDs, decisions).
4. **Schema validation drops junk.** `_SCHEMAS` whitelists which keys the router may contribute and their accepted types.
5. **Confidence threshold.** Only responses with `confidence >= MIN_AI_CONFIDENCE` (default 0.75) are merged.
6. **Telemetry tracks paths.** `ai_path` = `deterministic` | `hybrid` | `router_error` is logged per module.

---

## Architecture

### Request flow

```
Backend AI client (ai_client.py)
  └─ POST http://localhost:8001/v1/{module}  {"payload": {...}}
       └─ modules/{module}.run(payload)     [ai/app/main.py]
            ├─ fallbacks/{module}.py         → baseline (deterministic, always runs)
            ├─ router_client.enhance(module, payload, baseline)
            │     ├─ route(): POST {AI_ROUTER_URL}/chat/completions  (OpenAI format)
            │     │     → parse choices[0].message.content as JSON
            │     └─ merge: shallow-merge into baseline, skipping _AI_IMMUTABLE keys
            └─ validated result returned
```

### Key modules

| Module | File | Deterministic Baseline | AI Enhancement | Immutable Keys |
|--------|------|----------------------|----------------|----------------|
| Diagnostics | `ai/app/modules/diagnostics.py` | `diagnose_fallback()` | `enhance("diagnostics", ...)` | summary, severity, items[*].*, confidence |
| Service prediction | `ai/app/modules/service_prediction.py` | `predict_service_fallback()` | `enhance("service-prediction", ...)` | service_type, interval_km, next_due_* |
| OCR | `ai/app/modules/ocr.py` | `extract_receipt_fallback()` (Tesseract) | `enhance("ocr", ...)` | vendor, invoice_date, total, tax, currency, items |
| Resale | `ai/app/modules/resale.py` | `estimate_value_fallback()` | `enhance("resale", ...)` | estimated_value, low, high, currency |
| Mod impact | `ai/app/modules/mod_impact.py` | `mod_impact_fallback()` | `enhance("mod-impact", ...)` | performance_score, value_impact, reliability_impact |
| Condition | `ai/app/modules/condition.py` | `estimate_condition()` | `enhance("condition", ...)` | (summary only — AI adds narrative) |
| Fuel OCR | `ai/app/modules/fuel_ocr.py` | `_fuel_receipt_fallback()` (Tesseract) | `enhance("fuel-ocr", ...)` | vendor, date, litres, price_per_litre, total_cost, currency |
| Parts guide | `ai/app/modules/parts_guide.py` | `build_inventory_from_categories()` + `suggest_parts_for_service()` | `enhance("parts-guide", ...)` | sku, service_group, supplier |
| Advisor | `ai/app/services/advisor/` | `advisor_fallback()` | `enhance("advisor", ...)` | decision, based_on |
| Car check | `ai/app/modules/car_check.py` | `car_check_fallback()` | `enhance("car-check", ...)` | deal_score, red_flags, green_flags |
| Odometer | `ai/app/modules/odometer.py` | `_odometer_fallback()` (Tesseract) | **None** — deterministic only | — |
| Social image | `ai/app/modules/social_image.py` | `render_card()` (Pillow) | Pollinations.ai (optional) | — |

---

## Configuration

Environment variables:

| Variable | Purpose | Default |
|----------|---------|---------|
| `AI_ROUTER_URL` | 9Router OpenAI-compatible endpoint | `http://10.0.3.17:20128/v1` |
| `AI_ROUTER_API_KEY` | Bearer token for router | (none) |
| `AI_ROUTER_MODEL` | Model served by router | `General-Use` |
| `AI_ROUTER_TIMEOUT_SECONDS` | Per-request timeout | `120` |
| `AI_ENABLED` | Master switch for all AI | `true` |
| `MIN_AI_CONFIDENCE` | Minimum confidence for merge | `0.75` |

Setting `AI_ENABLED=false` forces every module into deterministic-only mode — useful for cost control, incident response, or offline deploys.

---

## Adding a New AI Module

1. Create `ai/app/modules/<module>.py` with a `<module>_fallback()` function that returns the complete baseline result.
2. Add a system prompt in `ai/app/router_utils.py::_SYSTEM_PROMPTS` with a strict JSON contract.
3. Add `_AI_IMMUTABLE[module]` — keys the rule engine produces that the router must never overwrite.
4. Add `_SCHEMAS[module]` — whitelist of keys/types the router may contribute.
5. Register the module route in `ai/app/main.py`.
6. Add telemetry: `enhance()` already records `ai_path` per module.
7. Document the module in this file's table.

---

## Telemetry

`ai/app/router_client.py::_AI_TELEMETRY` tracks per-module path counts:

```python
{"diagnostics": {"deterministic": 42, "hybrid": 15, "router_error": 3}}
```

Exposed via `GET /v1/telemetry`. Reset with `ai_telemetry_reset()`.

---

## Failure Behaviour

| Failure mode | Router response | System behaviour |
|-------------|----------------|------------------|
| Router disabled (`AI_ENABLED=false`) | N/A | Deterministic baseline returned untouched |
| Router unreachable / timeout | Connection error | Deterministic baseline returned; `ai_path="router_error"` |
| HTTP 4xx/5xx | Status error | Deterministic baseline returned; `ai_path="router_error"` |
| Confidence < threshold | Low confidence | Deterministic baseline returned; `ai_path="deterministic"` |
| Malformed JSON | Parse error | Deterministic baseline returned; key dropped |
| Invalid type for key | Type mismatch | Key dropped; other valid keys still merged |
| Immutable key in response | Any | Key skipped; baseline value preserved |

The service stays fully functional with the router down. A complete gateway failure is a clean degradation, never a crash.
