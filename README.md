# AutoBrain

AI-powered car enthusiast companion. Manage vehicles, track maintenance & fuel,
run AI diagnostics, log modifications, scan receipts, manage parts inventory,
estimate resale value, and get analytics — all with an AI inference layer routed
through a [9Router](https://github.com/) instance.

## Architecture

```
┌────────────┐   REST / WebSocket   ┌──────────────────────────────┐
│  Flutter   │ ───────────────────▶ │         FastAPI backend       │
│  (iOS/And) │ ◀─────────────────── │  REST + WS + Celery workers   │
└────────────┘                      └──────┬──────────┬─────────────┘
                                           │          │
                               PostgreSQL  │          │  Redis / Celery
                               MinIO (S3)  │          │
                                           ▼          ▼
                                ┌──────────────────────────────────┐
                                │  AI inference layer (FastAPI)    │
                                │  5 modules: diagnostics, service │
                                │  prediction, OCR, resale, mod    │
                                │  impact                          │
                                └──────────────┬───────────────────┘
                                               │ AI_ROUTER_URL
                                               ▼
                                      ┌────────────────┐
                                      │  9Router       │
                                      │  (LLM router)  │
                                      └────────────────┘
```

## Quick start (local dev)

```bash
cp .env.example .env
docker compose up --build
```

- API docs: http://localhost:8000/docs
- AI gateway docs: http://localhost:8001/docs
- MinIO console: http://localhost:9001 (minioadmin/minioadmin)

## Stack

| Layer      | Tech                                                        |
|------------|-------------------------------------------------------------|
| Backend    | Python FastAPI, SQLAlchemy 2 (async), Pydantic v2           |
| DB         | PostgreSQL 16, Redis 7, MinIO (S3-compatible storage)       |
| Workers    | Celery + Redis broker                                       |
| AI         | Python FastAPI gateway, routes to 9Router via `AI_ROUTER_URL` |
| Frontend   | Flutter (iOS + Android), offline-first, local cache          |
| Infra      | Docker Compose, Kubernetes manifests, systemd, GitHub Actions |

## AI modules

| Module              | Purpose                                    |
|---------------------|--------------------------------------------|
| diagnostics         | Symptoms → likely causes, severity, parts, cost |
| service_prediction  | Next service due given history + schedule  |
| ocr                 | Receipt/invoice → parts, labour, cost, warranty |
| resale              | Value estimate + trend + recommendations  |
| mod_impact          | Performance/value impact of modifications  |

All modules read `AI_ROUTER_URL` at runtime and POST inference requests to
`{AI_ROUTER_URL}/v1/{module}`. If the router is unreachable a deterministic
rule-based fallback runs locally so the platform never breaks.

## Documentation

Full documentation is maintained in the team wiki (Outline) and mirrored under
[`docs/`](docs/). See [`docs/README.md`](docs/README.md).

## License

MIT — see [LICENSE](LICENSE).
