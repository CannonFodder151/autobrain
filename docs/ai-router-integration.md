# AI Router Integration (9Router)

Every AI feature is routed through an external LLM router instance identified
by the `AI_ROUTER_URL` environment variable. The router is called in OpenAI
chat-completions format.

## Requirement

All AI modules **must** read `AI_ROUTER_URL` at runtime. The AI gateway
(`ai/app/router_client.py`) does this on every request:

```python
def router_url() -> str:
    return os.getenv("AI_ROUTER_URL", "http://your-9router-instance:port/v1").rstrip("/")
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
            ├─ router_client.route(module, payload)
            │    └─ POST {AI_ROUTER_URL}/chat/completions   (OpenAI format)
            │         {"model": ..., "messages": [system+user], "stream": false}
            │    → parse choices[0].message.content as JSON
            └─ on failure → fallbacks.py deterministic engine
```

## Failure behaviour

- Router unreachable / HTTP error / timeout → `route()` returns `None` →
  module runs the fallback.
- Fallback output matches the router output schema (both carry `model`).
- LLM output variance (missing/null optional fields) is absorbed by tolerant
  backend schemas and module-level normalization (e.g. service prediction
  recomputes missing dates).
- A complete gateway failure is a clean 503, never a crash.

## Router contract

9Router exposes an OpenAI-compatible `POST /v1/chat/completions`. The gateway
sends a strict-JSON system prompt per module, so the model reply parses
directly into the module output schema. Configure your 9Router instance with
routing for the model set in `AI_ROUTER_MODEL`.
