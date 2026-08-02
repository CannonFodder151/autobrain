# AI Models

All five modules live in `ai/app/modules/` and are exposed by the gateway at
`/v1/{module}`. Each module first POSTs the inference request to 9Router and
falls back to a deterministic rule-based engine if the router is unreachable.
The response includes a `model` field (`"9router"` or `"rule-based-fallback"`)
so callers know which path produced it.

| Module | Endpoint | Input | Output |
|--------|----------|-------|--------|
| Diagnostics | `/v1/diagnostics` | symptoms, vehicle context, OBD codes | causes w/ confidence + severity, parts, cost estimate, recommended actions |
| Service prediction | `/v1/service-prediction` | make/model/year, odometer, last service, service type | interval, next due km + date, confidence, reason |
| OCR | `/v1/ocr` | file metadata + content preview | vendor, date, total, tax, items (part/labour), warranty, next service |
| Resale | `/v1/resale` | vehicle attributes, service history, mods, condition | value low/est/high, factor breakdown, recommendations |
| Mod impact | `/v1/mod-impact` | mod name, category, vehicle, notes | performance score, value impact, reliability impact |

## Fallback engines

`ai/app/fallbacks.py` implements the offline paths:

- **Diagnostics:** keyword rules for symptoms (brakes, vibration, leaks,
  noises…) + OBD code table (P0300, P0420, P0171, …) mapped to parts/costs.
- **Service prediction:** manufacturer schedule table per service type with
  make-specific interval multipliers.
- **OCR:** line-scan heuristics for vendor, item hints and totals.
- **Resale:** base value per make/model, age + odometer depreciation curves,
  condition and service-history multipliers.
- **Mod impact:** per-category performance/value/reliability table.

## Contract

The gateway calls the router with:

```
POST {AI_ROUTER_URL}/v1/{module}
{
  "payload": { ...module input... }
}
```

Router response is expected as either the raw result JSON or `{"result": ...}`.
