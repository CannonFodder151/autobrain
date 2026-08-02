# AI Router Integration (9Router)

Every AI feature is routed through an external LLM router instance identified
by the `AI_ROUTER_URL` environment variable.

## Requirement

All AI modules **must** read `AI_ROUTER_URL` at runtime. The AI gateway
(`ai/app/router_client.py`) does this on every request:

```python
def router_url() -> str:
    return os.getenv("AI_ROUTER_URL", "http://your-9router-instance:port").rstrip("/")
```

## Configuration

`.env`:

```
AI_ROUTER_URL=http://your-9router-instance:port
AI_ROUTER_API_KEY=            # optional bearer token
AI_ROUTER_TIMEOUT_SECONDS=60
```

The placeholder value `http://your-9router-instance:port` explicitly disables
routing — the gateway then always uses the local fallback so the platform
runs end-to-end without a router.

## Request flow

```
backend (ai_client.py)
  └─ HTTP POST http://ai:8001/v1/{module}
       └─ modules/{module}.run(payload)
            ├─ router_client.route("diagnostics", payload)
            │    └─ POST {AI_ROUTER_URL}/v1/diagnostics  {"payload": {...}}
            └─ on failure → fallbacks.py deterministic engine
```

## Failure behaviour

- Router unreachable / HTTP error / timeout → `route()` returns `None` →
  module runs the fallback.
- Fallback output matches the router output schema (both carry `model`).
- The backend treats a complete gateway failure as a clean 503, never a crash.

## Router module contract

The router should expose `POST /v1/{module}` accepting `{"payload": {...}}`
and returning either the result object directly or `{"result": {...}}`.
Configure your 9Router instance with routes for: `diagnostics`,
`service-prediction`, `ocr`, `resale`, `mod-impact`.
