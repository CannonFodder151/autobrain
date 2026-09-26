# AI Router Integration (9Router)

Every AI feature is optionally routed through an external LLM router instance
identified by the `AI_ROUTER_URL` environment variable. The router is called in
OpenAI chat-completions format. AutoBrain is **deterministic-first**: the
rule-based engine always runs and produces the result; 9Router only enriches it
when reachable, and can never override measured ground-truth values.

## Immutable Key Rationale

### Why `_AI_IMMUTABLE` keys exist

AutoBrain adopts a **deterministic-first architecture** for all AI modules:

1. **Rule engine is authoritative** — every module runs a deterministic baseline
   engine (in `ai/app/fallbacks/`) that produces a complete, valid result with no
   LLM involvement. That baseline is the *ground truth*.
2. **LLM is enrichment only** — the 9Router LLM is called *after* the baseline and
   its output is shallow-merged in. It may fill gaps, add narrative advice, or
   contribute market facts; it never replaces measured numbers.
3. **Immutable keys are the enforcement mechanism** — the `_AI_IMMUTABLE` map in
   `ai/app/router_utils.py` lists the keys per module that are ground truth and
   must never be overridden. This is a hard guardrail: if the model hallucinates a
   different `estimated_value` or `vendor`, the merge loop skips those keys.

Why it matters:

- **Reliability** — the platform works end-to-end even when 9Router is down,
  unreachable, or misconfigured.
- **Auditability** — measured values (odometer readings, invoice totals,
  RRP-anchored valuations) are traceable to deterministic code, not model output.
- **Safety** — financial and safety-critical numbers (resale estimates, fuel
  costs, OBD diagnostics) cannot be altered by LLM variance.

### How immutable keys enforce deterministic paths

Enforcement lives in `ai/app/router_client.py`, in `enhance()`. Four independent
gates must all pass before any router field is merged; each failure returns the
deterministic baseline untouched.

```python
# Simplified merge logic (ai/app/router_client.py)
async def enhance(module: str, payload: dict, baseline: dict) -> dict:
    result = await route(module, payload)          # gate 0: None on any failure
    if not isinstance(result, dict):
        return baseline

    conf_val = float(result.get("confidence") or 0.0)
    if conf_val < float(os.getenv("MIN_AI_CONFIDENCE", "0.75")):   # gate 1
        return baseline

    merged = dict(baseline)
    enriched = False
    immutable = _AI_IMMUTABLE.get(module, frozenset())
    schema = _SCHEMAS.get(module, {})

    for key, value in result.items():
        if key == "model" or key in immutable:        # gate 2: immutable keys
            continue
        if key not in schema or not _matches_type(value, schema[key]):
            continue                                  # gate 3: schema whitelist
        if not _validate_nested(value):
            continue                                  # gate 3b: depth <= 4, list <= 100
        merged[key] = value
        enriched = True

    if enriched:
        merged["model"] = "rule-based+ai"
    return merged
```

Key properties:

- Immutable keys are *per-module* — each module declares its own ground truth.
- The check is a single `continue` in the merge loop — no ambiguity, no override
  path.
- `_SCHEMAS` is a second layer: a non-immutable key absent from the whitelist is
  dropped even if the model invented it.
- `_validate_nested` is a third layer: nesting deeper than 4 levels, or arrays
  longer than 100 items, is dropped.
- `MIN_AI_CONFIDENCE` (default `0.75`) is a fourth layer: a low-confidence
  response is treated as though the router had not answered.
- `AI_ENABLED=false` is the master switch — forces every module deterministic-only
  (incident response, cost control, offline deploys).
- Dropped keys are logged (`router_dropped_key`, `router_dropped_key_nested`) so
  suppressions are auditable rather than silent.

### AI fallback behaviour

| Scenario | What happens | `model` field value |
|----------|--------------|---------------------|
| `AI_ENABLED=false` | Router disabled — baseline returned immediately | `rule-based-fallback` / module baseline |
| `AI_ROUTER_URL` unset or still the `your-9router-instance` placeholder | Router disabled — baseline returned immediately | `rule-based-fallback` / module baseline |
| Router HTTP error / timeout / DNS failure | `route()` catches the exception, returns `None` — baseline | `rule-based-fallback` |
| Response body exceeds 1 MiB | Oversized response dropped — baseline | `rule-based-fallback` |
| Router returns invalid or non-JSON content | `_clean_json` raises, caught — baseline | `rule-based-fallback` |
| Response below `MIN_AI_CONFIDENCE` | Low-confidence response rejected — baseline | `rule-based-fallback` |
| At/above threshold, but all fields immutable or off-schema | Nothing enrichable — baseline | module baseline value |
| At/above threshold, at least one field passes all gates | Shallow merge, immutable keys protected | `rule-based+ai` |
| Response with `null` / missing optional fields | Those keys do not merge — baseline values preserved | `rule-based+ai` (partial) |

**Critical guarantee**: in every failure mode the deterministic baseline is
returned. The platform never degrades to an error state because the AI is
unavailable — it degrades to *deterministic-only mode*, the designed baseline
capability. A complete gateway failure surfaces as a clean 503, never a crash.

### Telemetry

`enhance()` records one `ai_path` log line per call and keeps in-process counters
(exposed at `/v1/telemetry` via `ai_telemetry_snapshot()`):

- `deterministic` — router disabled, unreachable, low confidence, or no
  enrichable fields
- `hybrid` — the router contributed at least one field
- `router_error` — the router returned an HTTP error or raised

## Requirement

All AI modules **must** read `AI_ROUTER_URL` at runtime. The AI gateway
(`ai/app/router_client.py`) does this on every request, and every module must
work with the router down (deterministic fallback):

```python
def router_url() -> str:
    return os.getenv("AI_ROUTER_URL", "http://10.0.3.17:20128/v1").rstrip("/")

def router_enabled() -> bool:
    ai_enabled = os.getenv("AI_ENABLED", "true").strip().lower()
    if ai_enabled in ("false", "0", "no"):
        return False
    url = router_url()
    return bool(url) and "your-9router-instance" not in url
```

## Configuration

`.env`:

```
AI_ENABLED=true
AI_ROUTER_URL=http://10.0.3.17:20128/v1
AI_ROUTER_API_KEY=
AI_ROUTER_MODEL=General-Use
AI_ROUTER_TIMEOUT_SECONDS=120
MIN_AI_CONFIDENCE=0.75
```

The canonical endpoint is `http://10.0.3.17:20128/v1` (on-prem 9Router; dev/demo
stacks use it via `.env`). The Oracle-hosted stack overrides this to its
stack-local `9router` service because `10.0.3.17` is unreachable from Oracle
Cloud. If `AI_ROUTER_URL` is left at the old placeholder
`http://your-9router-instance:port/v1`, routing is disabled and the gateway
always uses the local fallback so the platform runs end-to-end without a router.
Check available models with `GET {AI_ROUTER_URL}/models`.

## Request flow

```
backend (ai_client.py)
  └─ HTTP POST http://localhost:8001/v1/{module}   {"payload": {...}}
       └─ modules/{module}.run(payload)   [ai_app/main.py]
            ├─ fallbacks/{module}.py  → baseline (deterministic, always runs)
            ├─ router_client.enhance(module, payload, baseline)
            │    └─ route(): POST {AI_ROUTER_URL}/chat/completions   (OpenAI format)
            │         {"model": AI_ROUTER_MODEL,
            │          "messages": [system+untrusted-data+user],
            │          "temperature": 0, "stream": false}
            │    → parse choices[0].message.content as JSON
            │    → shallow-merge into baseline, skipping _AI_IMMUTABLE keys
            └─ validated, clamped result
```

Note: In dev and prod stacks, the AI gateway runs inside the backend container
on :8001 (alongside the API on :8000 and Celery worker+beat). In the hosted
stack, the AI gateway runs in a separate `ai` container (AUT-1242/C3) because
it also hosts the market-data scraper.

Inbound payloads are capped per-field (`_FIELD_MAX_LEN`) and in total (100 000
chars), and are wrapped in an `<untrusted_user_data>` block with an explicit
prompt-injection guard, so user text cannot become instructions.

## Immutable keys (ground truth)

`_AI_IMMUTABLE` in `ai/app/router_utils.py` protects deterministic-critical keys
per module. The rule engine runs first and its result is always returned. When
the router responds, `enhance()` shallow-merges its fields into the baseline,
**skipping any key listed in `_AI_IMMUTABLE`** (and any key outside the module's
`_SCHEMAS` whitelist). The router can never override measured numbers,
identifiers, currency, or value ranges — it may only fill gaps and add advice.

```python
# ai/app/router_utils.py
_AI_IMMUTABLE: dict[str, frozenset[str]] = {
    "resale": frozenset({"estimated_value", "low", "high", "currency"}),
    "mod-impact": frozenset({"performance_score", "value_impact", "reliability_impact"}),
    "ocr": frozenset({"vendor", "invoice_date", "total", "tax", "currency", "items"}),
    "fuel-ocr": frozenset({"vendor", "date", "litres", "price_per_litre", "total_cost", "currency"}),
    "advisor": frozenset({"decision", "based_on"}),
    "car-check": frozenset({"deal_score", "red_flags", "green_flags"}),
    "diagnostics": frozenset({"summary", "severity", "items", "parts_needed", "recommended_actions"}),
    "service-prediction": frozenset({"service_type", "interval_km", "interval_months", "next_due_km", "next_due_date"}),
}
```

### Rationale per module

| Module | Immutable keys | Why these are ground truth | Router may add |
|--------|----------------|----------------------------|----------------|
| **resale** | `estimated_value`, `low`, `high`, `currency` | Baseline uses RRP-anchored depreciation curves (base value, age/odometer multipliers, condition and service-history factors) plus a live market-data median anchor. Authoritative valuation. | `rrp`, `used_price`, `factors`, `recommendations`, `trend`, `confidence` |
| **mod-impact** | `performance_score`, `value_impact`, `reliability_impact` | Scores come from a deterministic per-category table. | `summary`, `confidence` |
| **ocr** | `vendor`, `invoice_date`, `total`, `tax`, `currency`, `items` | Line-scan + Tesseract extracts these from the receipt image. Measured facts. | `next_recommended_service`, `warranty_notes`, `confidence` |
| **fuel-ocr** | `vendor`, `date`, `litres`, `price_per_litre`, `total_cost`, `currency` | Direct fuel receipt extraction. | `notes`, `confidence` |
| **advisor** | `decision`, `based_on` | The deterministic engine produces the keep/upgrade/delay/strategy decision and its evidence dict. | `rationale`, `next_actions`, `confidence` |
| **car-check** | `deal_score`, `red_flags`, `green_flags` | The deterministic engine computes the deal score and extracts the structured listing flags. | `summary`, `confidence` |
| **diagnostics** | `summary`, `severity`, `items`, `parts_needed`, `recommended_actions` | The deterministic engine produces the full diagnostic tree (causes, parts, actions). | `estimated_cost`, `cost_range`, `confidence` |
| **service-prediction** | `service_type`, `interval_km`, `interval_months`, `next_due_km`, `next_due_date` | Intervals come from manufacturer specs cross-checked against actual service history. | `due_in_km`, `due_in_days`, `reason`, `confidence` |

Modules **not** in `_AI_IMMUTABLE`:

- **condition** — the deterministic engine already infers the label; the router
  only writes a narrative `summary` (the schema allows nothing else).
- **parts-guide** — the router may only tidy `description`, `brand` casing, and
  `category` normalisation inside `parts`; `sku`, `supplier`, and `service_group`
  stay deterministic and off-schema.
- **odometer** — deterministic-only (Tesseract + regex); the router is never
  called.

All router calls run at **temperature 0** for repeatable outputs.

## Failure behaviour

- Router disabled / unreachable / HTTP error / timeout / oversized response →
  `route()` returns `None` → the module returns the **deterministic baseline**
  untouched.
- `enhance()` protects per-module immutable keys (`_AI_IMMUTABLE`): measured
  numbers, identifiers, currency and value ranges are ground truth and can
  never be overridden by the model — it may only fill in gaps and add advice.
- Confidence gate (`MIN_AI_CONFIDENCE`, default 0.75): low-confidence responses
  are treated as deterministic-only.
- The `model` field reports the path: `rule-based-fallback` /
  `rrp-depreciation` (resale baseline) / `rule-based+ai` (enriched).
- LLM output variance (missing/null optional fields) is absorbed by tolerant
  backend schemas and module-level normalization (e.g. service prediction
  recomputes missing dates).
- A complete gateway failure is a clean 503, never a crash.

## Router contract

9Router exposes an OpenAI-compatible `POST /v1/chat/completions`. The gateway
sends a strict-JSON system prompt per module, so the model reply parses
directly into the module output schema. Configure your 9Router instance with
routing for the model set in `AI_ROUTER_MODEL`.
