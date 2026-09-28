# Developer Onboarding

## 1. Get the repo

```bash
git clone git@github.com:CannonFodder151/autobrain.git
cd autobrain
```

## 2. Local stack

Requires Docker + Compose. No local Python/Flutter needed for backend/AI.

```bash
cp .env.example .env
docker compose up -d --build
```

The dev stack runs **5 containers**: postgres, redis, minio, backend (API + AI gateway + Celery worker+beat), frontend. The AI gateway runs as a subprocess on `:8001` inside the backend container (AUT-3461). All app containers run as non-root (`autobrain` uid 1000) with healthchecks.

## 3. Verify

- `curl http://localhost:8000/health` → `{"status":"ok",...}`
- `curl http://localhost:8001/health` → AI gateway status
- `curl http://localhost:8000/docs` → OpenAPI spec
- `curl http://localhost:20128/health` → 9Router status (requires 9Router running separately or via Docker)

## 4. Code layout

```
backend/   FastAPI + SQLAlchemy + Celery   (app/ = package)
ai/        inference gateway + fallbacks   (app/ = package)
frontend/  Flutter web app                 (lib/ = package)
docker/    build contexts for all images   (backend/, ai/, frontend/ incl. nginx confs)
infra/     k8s + systemd manifests
scripts/   deploy, backup, setup-server, publish-images, bump-version, check-release
tests/     backend + ai tests
docs/      markdown mirrors of the wiki
```

> **Mobile app:** the iOS/Android app lives in the separate **private** repo
> `CannonFodder151/autobrain-mobile`. This repo's `frontend/` is the Flutter
> **web** build only; the two share a common Flutter lineage and the same
> release version (`scripts/bump-version.sh --mobile`).

## 5. Day-to-day

- **Add an endpoint** → `backend/app/api/v1/<area>.py` + `schemas/<area>.py`, register in `api/v1/__init__.py`.
- **Add a table** → model in `backend/app/models/`, autogenerate migration.
- **Add an AI feature** → module in `ai/app/modules/` + rule engine in `ai/app/fallbacks/` (deterministic first) + client fn in `backend/app/services/ai_client.py`.
- **Add a screen** → `frontend/lib/screens/<area>/`.

### Feature parity (web + mobile)

Every feature is built for **both** frontends at the same time:
- **Web** = `frontend/` in this repo (hosted at autobrainservice.app).
- **Mobile** = the private `CannonFodder151/autobrain-mobile` repo (same Flutter lineage).
- A feature is not done until the screen/flow exists in **both**. If it adds a
  screen, add it in `frontend/lib/screens/` here and mirror it into
  `autobrain-mobile/lib/` (see `docs/mobile-release.md`).
- **OBD2 integration is the only exception** — mobile-only, never on the website.

### Changelog

- One shared changelog (`CHANGELOG.md`) covers **both** the hosted and mobile
  apps — no separate mobile changelog.
- Every feature or user-facing change adds an entry under `[Unreleased]` in the
  same PR that ships it. Frontend-only changes count too.

## 6. Tests

```bash
docker compose exec backend pytest
# ai/ tests run inside the same backend container (ai/ is packaged as ai_app):
docker compose exec backend pytest /app/tests/ai
# frontend:
cd frontend && flutter test
```

## 7. Docs

Behaviour changes update BOTH the Outline wiki (AutoBrain collection) and `docs/` mirror.

## 8. Rego / market data providers

External lookups (`REGO_LOOKUP_URL`, `MARKET_DATA_URL`) are optional; see `.env.example`. Without them the app uses deterministic offline heuristics.

## 9. AI routing

Every AI feature is optionally routed through 9Router (`AI_ROUTER_URL`). AutoBrain is
**deterministic-first**: the rule-based engine always runs and produces the result;
9Router only enriches it when reachable, and can never override measured ground-truth
values. Set `AI_ROUTER_URL=http://10.0.3.17:20128/v1` for the on-prem 9Router, or
`http://9router:20128/v1` for the hosted stack's local router. If left unset, the
gateway always uses the local fallback so the platform runs end-to-end.

## 10. Federation hub

The Community Garage federation hub (`SOCIAL_FEDERATION_HUB_URL`) is optional.
Self-hosters default to `hosted=false` (pay $20/yr). The hosted stack registers
`hosted=true` with its own hub instance. See `docs/Engineering/ai/vector.md` and
the hub's private repo for details.
