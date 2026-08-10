# AI Router Integration (9Router)

Every AI feature is optionally routed through an external LLM router instance
identified by the `AI_ROUTER_URL` environment variable. The router is called in
OpenAI chat-completions format. AutoBrain is **deterministic-first**: the
rule-based engine always runs and produces the result; 9Router only enriches it
when reachable, and can never override measured ground-truth values.

## Requirement

All AI modules **must** read `AI_ROUTER_URL` at runtime. The AI gateway
(`ai/app/router_client.py`) does this on every request, and every module must
work with the router down (deterministic fallback):

```python
def router_url() -> str:
    return os.getenv("AI_ROUTER_URL", "http://your-9router-instance:port/v1").rstrip("/")

def router_enabled() -> bool:
    url = router_url()
    return bool(url) and "your-9router-instance" not in url
```

## Configuration

`.env`:

```
AI_ROUTER_URL=http://your-9router-instance:port/v1
AI_ROUTER_API_KEY=
AI_ROUTER_MODEL=General-Use
AI_ROUTER_TIMEOUT_SECONDS=120
```

The placeholder value `http://your-9router-instance:port/v1` explicitly disables
routing — the gateway then always uses the local fallback so the platform
runs end-to-end without a router. Check available models with
`GET {AI_ROUTER_URL}/models`.

## Request flow

```
backend (ai_client.py)
  └─ HTTP POST http://ai:8001/v1/{module}   {"payload": {...}}
       └─ modules/{module}.run(payload)
            ├─ fallbacks/{module}.py  → baseline (deterministic, always runs)
            ├─ router_client.enhance(module, payload, baseline)
            │    └─ route(): POST {AI_ROUTER_URL}/chat/completions   (OpenAI format)
            │         {"model": AI_ROUTER_MODEL, "messages": [system+user],
            │          "temperature": 0, "stream": false}
            │    → parse choices[0].message.content as JSON
            │    → shallow-merge into baseline, skipping _AI_IMMUTABLE keys
            └─ validated, clamped result
```

## Failure behaviour

- Router disabled / unreachable / HTTP error / timeout → `route()` returns
  `None` → the module returns the **deterministic baseline** untouched.
- `enhance()` protects per-module immutable keys (`_AI_IMMUTABLE`): measured
  numbers, identifiers, currency and value ranges are ground truth and can
  never be overridden by the model — it may only fill in gaps and add advice.
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
